import ReactMarkdown, { type Components } from 'react-markdown'
import { cn } from '@/lib/utils'

const components: Components = {
  h1: ({ children }) => <h1 className="mb-1 mt-2 text-base font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1 mt-2 text-[15px] font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-1 mt-2 text-[13px] font-semibold">{children}</h4>,
  p: ({ children }) => <p className="my-1">{children}</p>,
  ul: ({ children }) => <ul className="my-1 list-disc pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal pl-5">{children}</ol>,
  li: ({ children }) => <li className="my-0.5">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-1 border-l-2 border-muted-foreground/30 pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  hr: () => <hr className="my-2 border-border" />,
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const text = Array.isArray(children) ? children.join('') : String(children ?? '')
    const isBlock = className?.includes('language-') || text.includes('\n')
    if (isBlock) {
      return (
        <code
          className={cn(
            'my-2 block overflow-x-auto whitespace-pre rounded-md bg-foreground/10 p-2.5 font-mono text-[12px] leading-relaxed',
            className
          )}
        >
          {children}
        </code>
      )
    }
    return <code className="rounded bg-foreground/10 px-1.5 py-0.5 font-mono text-[12px]">{children}</code>
  }
}

export default function Markdown({
  content,
  className
}: {
  content: string
  className?: string
}): JSX.Element {
  return (
    <div className={cn('text-[13px] leading-relaxed', className)}>
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  )
}
