import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Текст ответа в Markdown (списки, таблицы, жирный). HTML не отображается; ссылки открываются в новой вкладке. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="ai-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
        components={{ a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" /> }}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
