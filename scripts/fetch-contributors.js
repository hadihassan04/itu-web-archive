const fs = require('fs');
const path = require('path');

// GitHub repository: keepdying/itu-web-archive
const REPO_OWNER = 'keepdying';
const GITHUB_API_URL = `https://api.github.com/repos/keepdying/itu-web-archive/contributors`;

async function fetchContributors() {
  try {
    console.log('Fetching contributors from GitHub API...');
    
    const response = await fetch(GITHUB_API_URL, {
      headers: {
        'Accept': 'application/vnd.github.v3+json',
      },
    });

    if (!response.ok) {
      throw new Error(`GitHub API error: ${response.status} ${response.statusText}`);
    }

    const contributors = await response.json();
    
    // Filter out bots and format the data
    const formattedContributors = contributors
      .filter(contributor => contributor.type === 'User') // Exclude bots
      .map(contributor => ({
        username: contributor.login,
        profileUrl: contributor.html_url,
      }));

    // Ensure repo owner is included (may not be in contributors list)
    const ownerExists = formattedContributors.some(c => c.username === REPO_OWNER);
    if (!ownerExists) {
      formattedContributors.unshift({
        username: REPO_OWNER,
        profileUrl: `https://github.com/${REPO_OWNER}`,
      });
    }

    // Write to public folder
    const outputPath = path.join(__dirname, '..', 'public', 'contributors.json');
    fs.writeFileSync(
      outputPath,
      JSON.stringify(formattedContributors, null, 2),
      'utf-8'
    );

    console.log(`Successfully fetched ${formattedContributors.length} contributors`);
    console.log(`Written to ${outputPath}`);
  } catch (error) {
    console.error('Error fetching contributors:', error.message);
    console.log('Keeping existing contributors.json file');
    // Exit successfully - existing file will be used
  }
}

fetchContributors();