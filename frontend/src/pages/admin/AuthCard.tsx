import LockIcon from "@mui/icons-material/Lock";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

export function AuthCard({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", pt: { xs: 2, md: 6 } }}>
      <Paper sx={{ width: "100%", maxWidth: 480, p: { xs: 3, md: 4 }, display: "flex", flexDirection: "column", gap: 2.5 }}>
        <Avatar sx={{ bgcolor: "attribution.confidentBg", color: "primary.main", width: 48, height: 48 }}>
          <LockIcon />
        </Avatar>
        <Box>
          <Typography variant="h1">{title}</Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {intro}
          </Typography>
        </Box>
        {children}
      </Paper>
    </Box>
  );
}
