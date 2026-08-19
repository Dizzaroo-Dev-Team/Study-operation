import { useEffect, useRef, useState } from 'react';
import { Loader2, AlertCircle, FileText } from 'lucide-react';
import { config } from '@/config/config';

/**
 * DocxPreview - Renders DOCX files inline using docx-preview library
 * Uses backend proxy to fetch document content (bypasses CORS issues with Azure)
 */
export function DocxPreview({ documentId, file, className = '' }) {
  const containerRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if ((!documentId && !file) || !containerRef.current) return;

    let cancelled = false;

    const loadDocument = async () => {
      try {
        setLoading(true);
        setError(null);

        // Import docx-preview library
        const docxPreview = await import('docx-preview');
        let blob;

        if (file) {
          blob = file;
        } else {
          // Fetch the document via backend proxy (bypasses CORS)
          const proxyUrl = `${config.API_URL}/api/tmf/documents/${documentId}/content`;
          const response = await fetch(proxyUrl, {
            credentials: 'include',
            headers: {
              'Accept': 'application/octet-stream',
            }
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch document: ${response.status} - ${errorText}`);
          }

          blob = await response.blob();
        }

        if (cancelled) return;

        // Clear the container
        containerRef.current.innerHTML = '';

        // Render the DOCX
        await docxPreview.renderAsync(blob, containerRef.current, null, {
          className: 'docx-preview-wrapper',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          experimental: false,
          trimXmlDeclaration: true,
          useBase64URL: true,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
        });

        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          console.error('DOCX Preview Error:', err);
          setError(err.message || 'Failed to load document');
          setLoading(false);
        }
      }
    };

    loadDocument();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center h-full gap-4 p-8 ${className}`}>
        <div className="w-16 h-16 rounded-xl bg-red-100 flex items-center justify-center">
          <AlertCircle className="h-8 w-8 text-red-500" />
        </div>
        <div className="text-center space-y-2">
          <h3 className="text-base font-semibold text-slate-800">Failed to load document</h3>
          <p className="text-sm text-slate-500 max-w-xs">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative h-full w-full ${className}`}>
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white z-10">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <span className="text-sm text-slate-600">Loading document...</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="h-full w-full overflow-auto bg-white"
        style={{
          minHeight: '100%',
        }}
      />
      <style>{`
        .docx-preview-wrapper {
          padding: 20px;
          background: white;
        }
        .docx-preview-wrapper .docx-wrapper {
          background: white;
          padding: 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          margin: 0 auto;
        }
        .docx-preview-wrapper .docx-wrapper > section.docx {
          margin-bottom: 20px;
          box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }
      `}</style>
    </div>
  );
}

export default DocxPreview;
