import argparse
import asyncio
import json
import os
from datetime import datetime
from io import StringIO

import aiohttp
import pandas as pd
from tqdm import tqdm

DATE = str(datetime.now().date())
FOLDER_PATH = "public"
# All available program levels
PROGRAM_LEVELS = {
    "OL": "Associate",
    "LS": "Undergraduate",
    "LU": "Graduate",
    "LUI": "Graduate Level Evening Education"
}
BASE_URL = "https://obs.itu.edu.tr/public/DersProgram"
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
MAX_CONCURRENT_REQUESTS = 10  

# Headers to request English version
HEADERS = {
    'Accept-Language': 'en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7'
}

if not os.path.exists(FOLDER_PATH):
    os.makedirs(FOLDER_PATH)

if not os.path.exists(FOLDER_PATH + "/" + DATE):
    os.makedirs(FOLDER_PATH + "/" + DATE)


def exportJson(path: str, list: list):
    list = [{"value": v, "label": v} for v in list]
    with open(path, "w") as f:
        json.dump(list, f)


async def fetch_branch_codes(session: aiohttp.ClientSession, program_level: str):
    """Fetch branch codes and IDs from the API."""
    url = f"{BASE_URL}/SearchBransKoduByProgramSeviye?programSeviyeTipiAnahtari={program_level}"
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying branch codes fetch (attempt {attempt + 1}/{MAX_RETRIES})...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise Exception(f"Failed to fetch branch codes after {MAX_RETRIES} attempts: {e}")


async def gather_with_progress(coros, desc: str):
    """Gather async coroutines with tqdm progress bar."""
    pbar = tqdm(total=len(coros), desc=desc)
    
    async def track_progress(coro):
        try:
            result = await coro
            pbar.update(1)
            return result
        except Exception as e:
            pbar.update(1)
            raise
    
    tracked_coros = [track_progress(coro) for coro in coros]
    results = await asyncio.gather(*tracked_coros, return_exceptions=True)
    pbar.close()
    return results


async def fetch_course_data(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, program_level: str, branch_id: int, course_code: str):
    """Fetch course data for a specific branch ID."""
    url = f"{BASE_URL}/DersProgramSearch?ProgramSeviyeTipiAnahtari={program_level}&dersBransKoduId={branch_id}"
    
    async with semaphore:  # Limit concurrent requests
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response.raise_for_status()
                    text = await response.text()
                    
                    # Check if response contains a table
                    if "dersProgramContainer" not in text:
                        return None, course_code  # No data available
                    
                    # Parse HTML table using pandas
                    # pandas.read_html automatically extracts text from links by default
                    dfs = pd.read_html(StringIO(text))
                    if not dfs or len(dfs) == 0:
                        return None, course_code
                    
                    df = dfs[0]
                    
                    # Clean up column names:
                    # - Replace commas with semicolons to match original format
                    # - Normalize newlines and carriage returns (e.g., "Reservation\nMaj./Cap./Enrl.")
                    # - Strip whitespace
                    df.columns = [col.replace(",", ";").replace("\n", " ").replace("\r", "").replace("\x0D", "").replace("\x0A", " ").strip() 
                                 for col in df.columns]
                    
                    # Clean up data: strip whitespace from all string columns
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            df[col] = df[col].astype(str).str.strip()
                            # Replace 'nan' strings with empty strings
                            df[col] = df[col].replace('nan', '')
                    
                    return df, course_code
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    # Return None if we can't parse (likely no data)
                    return None, course_code


async def process_level(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, program_level: str, level_name: str, filter_courses: set = None):
    """Process a single program level asynchronously."""
    print(f"\n{'='*60}")
    print(f"Processing {level_name} ({program_level})...")
    print(f"{'='*60}")
    
    # Fetch branch codes for this level
    print(f"Fetching branch codes for {level_name}...")
    branch_data = await fetch_branch_codes(session, program_level)
    
    if not branch_data:
        print(f"No branch codes found for {level_name}, skipping...")
        return set(), 0
    
    course_codes = [item["dersBransKodu"] for item in branch_data]
    branch_ids = {item["dersBransKodu"]: item["bransKoduId"] for item in branch_data}
    
    # Filter by course codes if specified
    if filter_courses:
        course_codes = [code for code in course_codes if code in filter_courses]
        if not course_codes:
            print(f"No matching course codes found for {level_name} with filter: {filter_courses}")
            return set(), 0
        print(f"Filtered to {len(course_codes)} course codes: {', '.join(course_codes)}")
    
    print(f"Found {len(course_codes)} course codes for {level_name}")
    
    # Create tasks for all course fetches
    tasks = [
        fetch_course_data(session, semaphore, program_level, branch_ids[course_code], course_code)
        for course_code in course_codes
    ]
    
    # Process all courses in parallel with progress bar
    processed_count = 0
    results = await gather_with_progress(tasks, desc=f"Processing {level_name}")
    
    # Save results to CSV files
    for result in results:
        # Handle exceptions that might have been returned
        if isinstance(result, Exception):
            continue  # Skip failed requests
        df, course_code = result
        if df is None or len(df) == 0:
            continue  # Skip courses with no data
        
        # Save to CSV with level prefix (except LS for backward compatibility)
        # LS files keep original format, other levels get prefix
        if program_level == "LS":
            csv_path = os.path.join(FOLDER_PATH, DATE, f"{course_code}.csv")
        else:
            csv_path = os.path.join(FOLDER_PATH, DATE, f"{program_level}-{course_code}.csv")
        df.to_csv(csv_path, index=True)
        processed_count += 1
    
    print(f"Processed {processed_count} courses for {level_name}")
    return set(course_codes), processed_count


async def main():
    parser = argparse.ArgumentParser(description='Fetch ITU course schedules from API')
    parser.add_argument('--courses', '-c', nargs='+', help='Filter by specific course codes (e.g., BBF AKM)')
    parser.add_argument('--level', '-l', choices=list(PROGRAM_LEVELS.keys()), help='Filter by specific education level')
    args = parser.parse_args()
    
    # Filter course codes if specified
    filter_courses = set(args.courses) if args.courses else None
    filter_level = args.level
    
    # Track course codes by level
    course_codes_by_level = {level: set() for level in PROGRAM_LEVELS.keys()}
    all_course_codes = set()
    
    # Process each program level
    levels_to_process = {filter_level: PROGRAM_LEVELS[filter_level]} if filter_level else PROGRAM_LEVELS
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Create aiohttp session
    async with aiohttp.ClientSession() as session:
        for program_level, level_name in levels_to_process.items():
            course_codes, _ = await process_level(session, semaphore, program_level, level_name, filter_courses)
            course_codes_by_level[program_level].update(course_codes)
            all_course_codes.update(course_codes)
    
    # Export metadata JSON files
    folders = [f.name for f in os.scandir(FOLDER_PATH) if f.is_dir()]
    exportJson(os.path.join(FOLDER_PATH, "dates.json"), sorted(folders))
    
    # Export course codes (kept for backward compatibility)
    exportJson(os.path.join(FOLDER_PATH, "course_codes.json"), sorted(all_course_codes))
    
    # Export detailed breakdown by level (used by frontend)
    course_codes_by_level_data = {
        "all": sorted(all_course_codes),
        "by_level": {level: sorted(codes) for level, codes in course_codes_by_level.items() if codes}
    }
    with open(os.path.join(FOLDER_PATH, "course_codes_by_level.json"), "w") as f:
        json.dump(course_codes_by_level_data, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Completed! Data saved to {FOLDER_PATH}/{DATE}/")
    print(f"Total unique course codes: {len(all_course_codes)}")
    if filter_courses:
        print(f"Filtered courses: {', '.join(sorted(filter_courses))}")
    if filter_level:
        print(f"Filtered level: {PROGRAM_LEVELS[filter_level]} ({filter_level})")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
