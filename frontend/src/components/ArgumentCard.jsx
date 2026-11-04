import ReactMarkdown from 'react-markdown'
import './ArgumentCard.css'

// The text comes from a language model that has read web content, so it is untrusted. It is rendered as Markdown
// (raw HTML is never interpreted), images are not allowed, and links open safely in a new tab.
const components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a>
  ),
}

const ArgumentCard = ({ title, content, type, icon }) => {
  return (
    <div className={`argument-card ${type}`}>
      <div className="card-header">
        <span className="card-icon">{icon}</span>
        <h3>{title}</h3>
      </div>
      <div className="card-content">
        {content ? (
          <ReactMarkdown disallowedElements={['img']} unwrapDisallowed components={components}>
            {content}
          </ReactMarkdown>
        ) : (
          <p className="placeholder-text">Waiting for analysis...</p>
        )}
      </div>
    </div>
  )
}

export default ArgumentCard
