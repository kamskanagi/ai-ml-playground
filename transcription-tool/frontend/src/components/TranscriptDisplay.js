import React, { useState } from 'react';

function TranscriptDisplay({ transcript, title, onCopy, onDownload }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(transcript);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    onCopy?.();
  };

  const handleDownload = () => {
    const blob = new Blob([transcript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.toLowerCase().replace(/\s+/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    onDownload?.();
  };

  return (
    <div className="transcript-display">
      <div className="transcript-header">
        <h3>{title}</h3>
        <div className="transcript-actions">
          <button onClick={handleCopy} className="btn btn-small" title="Copy to clipboard">
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button onClick={handleDownload} className="btn btn-small" title="Download as text file">
            Export
          </button>
        </div>
      </div>
      <div className="transcript-content">
        <pre>{transcript}</pre>
      </div>
    </div>
  );
}

export default TranscriptDisplay;
