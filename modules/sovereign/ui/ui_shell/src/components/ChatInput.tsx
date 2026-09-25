import { useState, type KeyboardEvent } from "react";

interface Props {
  /** Return false to keep the text (e.g. a LONG request the composer refused). */
  onSend: (text: string) => boolean | void;
  disabled?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, autoFocus, placeholder }: Props) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    if (onSend(text) === false) return;
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
        placeholder={placeholder ?? "Ask Sovereign..."}
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
