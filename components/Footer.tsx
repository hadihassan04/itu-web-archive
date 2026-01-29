import React, { useEffect, useState } from "react";
import { Box, Typography, Link } from "@mui/material";

interface Contributor {
  username: string;
  profileUrl: string;
}

const basePath = "/itu-web-archive";

const Footer: React.FC = () => {
  const [contributors, setContributors] = useState<Contributor[]>([]);

  useEffect(() => {
    fetch(`${basePath}/contributors.json`)
      .then((res) => res.json())
      .then(setContributors);
  }, []);

  const formatContributors = () => {
    if (contributors.length === 0) {
      return "@keepdying hayratıdır";
    }

    return (
      <>
        {contributors.map((contributor, index) => (
          <React.Fragment key={contributor.username}>
            <Link
              href={contributor.profileUrl}
              target="_blank"
              rel="noopener"
              underline="hover"
            >
              @{contributor.username}
            </Link>
            {index < contributors.length - 1 && (
              index === contributors.length - 2 ? " ve " : ", "
            )}
          </React.Fragment>
        ))} hayratıdır.
      </>
    );
  };

  return (
    <Box
      component="footer"
      sx={{
        py: 2, // padding top and bottom
        px: 2, // padding left and right
        mt: "auto", // push footer to bottom if content is short (requires parent to be flex column and child flex-grow:1)
        backgroundColor: (theme) =>
          theme.palette.mode === "dark"
            ? theme.palette.grey[900]
            : theme.palette.grey[200],
        borderTop: (theme) => `1px solid ${theme.palette.divider}`,
        textAlign: "center",
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {formatContributors()} -{" "}
        <Link
          href="https://github.com/keepdying/itu-web-archive"
          target="_blank"
          rel="noopener noreferrer"
          color="inherit"
        >
          GitHub Repository
        </Link>
      </Typography>
    </Box>
  );
};

export default Footer;
