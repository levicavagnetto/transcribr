import BrightnessAutoIcon from "@mui/icons-material/BrightnessAuto";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useColorScheme } from "@mui/material/styles";
import { useState } from "react";

const CHOICES = [
  { mode: "light", label: "Light", icon: <LightModeIcon fontSize="small" /> },
  { mode: "dark", label: "Dark", icon: <DarkModeIcon fontSize="small" /> },
  { mode: "system", label: "System", icon: <BrightnessAutoIcon fontSize="small" /> },
] as const;

export function ThemeMenu() {
  const { mode, setMode } = useColorScheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const current = CHOICES.find((c) => c.mode === (mode ?? "system")) ?? CHOICES[2];
  return (
    <>
      <IconButton
        color="inherit"
        aria-label={`Theme: ${current.label}`}
        aria-haspopup="menu"
        onClick={(event) => setAnchor(event.currentTarget)}
      >
        {current.icon}
      </IconButton>
      <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
        {CHOICES.map((choice) => (
          <MenuItem
            key={choice.mode}
            selected={choice.mode === current.mode}
            onClick={() => {
              setMode(choice.mode);
              setAnchor(null);
            }}
          >
            <ListItemIcon>{choice.icon}</ListItemIcon>
            {choice.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
