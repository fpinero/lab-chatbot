import { useRef, type PropsWithChildren } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { copy } from "../../lib/copy";

function CodeBlock({ children }: PropsWithChildren) {
  const ref = useRef<HTMLPreElement>(null);
  return (
    <div className="code-block">
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard
            .writeText(ref.current?.innerText ?? "")
            .catch(() => undefined);
        }}
      >
        {copy.copyCode}
      </button>
      <pre ref={ref}>{children}</pre>
    </div>
  );
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: CodeBlock,
          img: ({ alt }) => (
            <span>
              {copy.imageOmitted}
              {alt ? `: ${alt}` : ""}
            </span>
          ),
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
