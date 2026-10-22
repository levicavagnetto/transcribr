import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

// Placeholder shell; the real navigation, banner and views arrive in task group 9.
export function App() {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h1" component="div" sx={{ fontSize: 24, fontWeight: 700 }}>
            Transcribr
          </Typography>
        </Toolbar>
      </AppBar>
    </Box>
  );
}
