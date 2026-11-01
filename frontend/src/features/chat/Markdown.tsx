import {
  Children,
  isValidElement,
  useRef,
  type PropsWithChildren,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { copy } from "../../lib/copy";
import CopyButton from "./CopyButton";

function contentText(children: ReactNode): string {
  return Children.toArray(children)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number")
        return String(child);
      return isValidElement<{ children?: ReactNode }>(child)
        ? contentText(child.props.children)
        : "";
    })
    .join("");
}

function CodeBlock({ children }: PropsWithChildren) {
  const ref = useRef<HTMLPreElement>(null);
  return (
    <div className="code-block">
      <CopyButton
        contentKey={contentText(children)}
        text={() => ref.current?.innerText ?? ""}
        label={copy.copyCode}
        successMessage={copy.codeCopied}
        failureMessage={copy.codeCopyFailed}
        className=""
      />
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
