import { useState, type KeyboardEvent } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}

export function ChatInput({ onSend, disabled, autoFocus }: Props) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="chat-input">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask Sovereign..."
        rows={1}
        autoFocus={autoFocus}
        aria-label="Message input"
      />
      <button className="send" onClick={submit} disabled={disabled || !value.trim()}>
        Send
      </button>
    </div>
  );
}
