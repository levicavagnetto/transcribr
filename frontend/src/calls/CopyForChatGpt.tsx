import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import type { CallDetail, Segment } from "../api/hooks";
import { chatGptText, copyToClipboard } from "../copy";
import { monoFontFamily } from "../theme";

interface Props {
  call: CallDetail;
  segments: Segment[];
  prompt: string;
}

export function CopyForChatGpt({ call, segments, prompt }: Props) {
  const [includePhone, setIncludePhone] = useState(false);
  const [preview, setPreview] = useState(true);
  const [copied, setCopied] = useState(false);
  const [manual, setManual] = useState(false);
  const text = chatGptText(prompt, call, segments, includePhone);

  const copy = async () => {
    const result = await copyToClipboard(text);
    if (result === "manual") setManual(true);
    else setCopied(true);
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "12px 20px" }}>
        <Button variant="contained" startIcon={<ContentCopyIcon />} onClick={() => void copy()} sx={{ minHeight: 44 }}>
          Copy for ChatGPT
        </Button>
        <FormControlLabel
          control={<Checkbox checked={includePhone} onChange={(e) => setIncludePhone(e.target.checked)} />}
          label="Include the phone number"
        />
        <Button onClick={() => setPreview(!preview)} aria-expanded={preview} aria-controls="copy-preview">
          {preview ? "Hide what gets copied" : "Show what gets copied"}
        </Button>
      </Box>
      {preview && (
        <Box id="copy-preview" sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
            This is exactly what gets copied
          </Typography>
          <Box
            component="pre"
            data-testid="copy-preview-text"
            sx={{
              m: 0,
              p: 2,
              bgcolor: "background.default",
              border: 1,
              borderColor: "divider",
              borderRadius: 1,
              fontFamily: monoFontFamily,
              fontSize: 12.5,
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
              maxHeight: 320,
              overflow: "auto",
            }}
          >
            {text}
          </Box>
        </Box>
      )}
      <Snackbar
        open={copied}
        autoHideDuration={6000}
        onClose={() => setCopied(false)}
        message={`Copied for ChatGPT${includePhone ? ", with the phone number" : ""}. Paste it into a new chat.`}
      />
      <Dialog open={manual} onClose={() => setManual(false)} fullWidth maxWidth="md">
        <DialogTitle>Copy the text yourself</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            This browser blocked copying from the page. The text is selected below: press Ctrl+C (or Cmd+C on a Mac),
            then paste it into a new ChatGPT chat.
          </DialogContentText>
          <TextField
            value={text}
            multiline
            fullWidth
            minRows={8}
            maxRows={16}
            autoFocus
            label="Text for ChatGPT"
            onFocus={(e) => e.target.select()}
            slotProps={{ htmlInput: { readOnly: true } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setManual(false)}>Done</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
