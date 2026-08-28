import { useEffect, useRef } from "react";
import {
  isFailureJobStatus,
  type ChatMessage,
} from "../types/chat";
import { EvidenceLink } from "./EvidenceLink";

interface Props {
  messages: ChatMessage[];
}

/* How close to the bottom the reader must be for a new message to pull the
   view down. Past this, the reader is deliberately looking at earlier output
   and must not be yanked away from it. */
const NEAR_BOTTOM_PX = 120;

export function formatElapsedTime(elapsedSeconds: number): string {
  if (elapsedSeconds < 1) return `${Math.round(elapsedSeconds * 1_000)}ms`;
  if (elapsedSeconds < 10) return `${elapsedSeconds.toFixed(1)}s`;
  const roundedSeconds = Math.round(elapsedSeconds);
  if (roundedSeconds < 60) return `${roundedSeconds}s`;
  if (roundedSeconds < 3_600) {
    const minutes = Math.floor(roundedSeconds / 60);
    return `${minutes}m ${roundedSeconds % 60}s`;
  }
  const hours = Math.floor(roundedSeconds / 3_600);
  const minutes = Math.floor((roundedSeconds % 3_600) / 60);
  return `${hours}h ${minutes}m`;
}

export function formatTaskTokens(tokens: number | null): string {
  return tokens === null ? "unavailable" : tokens.toLocaleString("en-US");
}

export function ChatWindow({ messages }: Props) {
  const conversationRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

  const trackScrollPosition = () => {
    const element = conversationRef.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    nearBottom.current = distanceFromBottom <= NEAR_BOTTOM_PX;
  };

  useEffect(() => {
    if (!nearBottom.current) return;
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  return (
    <div
      className="conversation"
      ref={conversationRef}
      onScroll={trackScrollPosition}
    >
      <div className="conversation-inner">
        {messages.map((message) => {
          const messageStatus = message.job_status;
          const unacceptedOutput =
            message.role === "sovereign" &&
            messageStatus !== undefined &&
            messageStatus !== "completed";
          const failedOutput =
            messageStatus !== undefined &&
            isFailureJobStatus(messageStatus);
          return (
            <article
              key={message.id}
              className={`msg ${message.role}${
                unacceptedOutput ? " unaccepted" : ""
              }`}
              role={failedOutput ? "alert" : undefined}
            >
              <div className="msg-label">
                {message.role === "user" ? "You" : "Sovereign"}
                {message.route && (
                  <span className="message-route">{message.route}</span>
                )}
              </div>
              {unacceptedOutput ? (
                <div className="unaccepted-copy">
                  {messageStatus?.toUpperCase()}: no answer was accepted
                  {failedOutput ? "." : " yet."}
                  {message.error ? ` ${message.error}` : ""}
                </div>
              ) : (
                <div>{message.content}</div>
              )}
              {!unacceptedOutput &&
                message.role === "sovereign" &&
                message.metrics && (
                  <div className="output-metrics">
                    Tokens: {formatTaskTokens(message.metrics.tokens)} • Time:{" "}
                    {formatElapsedTime(message.metrics.elapsed_seconds)}
                  </div>
                )}
              {!unacceptedOutput && (
                <div className="message-meta">
                  <EvidenceLink evidence={message.evidence} />
                </div>
              )}
            </article>
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}
