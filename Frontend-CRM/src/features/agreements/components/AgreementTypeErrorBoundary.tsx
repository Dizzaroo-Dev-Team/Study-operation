import React from 'react'

interface Props {
  typeCode: string
  children: React.ReactNode
}

interface State {
  error: Error | null
}

export class AgreementTypeErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[Agreements/${this.props.typeCode}] panel crashed:`, error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="text-sm font-semibold text-red-900 mb-1">
            {this.props.typeCode} panel failed to render
          </div>
          <div className="text-xs text-red-800 font-mono break-all">
            {this.state.error.message}
          </div>
          <div className="text-xs text-red-700 mt-2">
            Other agreement types are unaffected. Check the console for details.
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default AgreementTypeErrorBoundary
