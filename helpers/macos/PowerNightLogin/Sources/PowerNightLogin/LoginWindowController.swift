import AppKit
import PowerNightLoginCore
import WebKit

/// Shows Tesla's sign-in page and intercepts its tesla://auth/callback redirect.
final class LoginWindowController: NSWindowController, WKNavigationDelegate, WKUIDelegate {
    private let webView: WKWebView
    private let hostLabel = NSTextField(labelWithString: "")
    private let statusLabel = NSTextField(labelWithString: "")
    private let onCallback: (String) -> Void

    init(origin: URL, onCallback: @escaping (String) -> Void) {
        self.onCallback = onCallback
        let configuration = WKWebViewConfiguration()
        // Every sign-in starts clean: no cookies or cache kept between runs
        configuration.websiteDataStore = .nonPersistent()
        webView = WKWebView(frame: .zero, configuration: configuration)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 780),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Tesla Sign-In for PowerNight"
        window.center()
        super.init(window: window)

        webView.navigationDelegate = self
        webView.uiDelegate = self

        let serverLabel = NSTextField(labelWithString: "For PowerNight at \(origin.absoluteString)")
        serverLabel.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        serverLabel.textColor = .secondaryLabelColor
        hostLabel.font = .monospacedSystemFont(ofSize: NSFont.smallSystemFontSize, weight: .regular)
        statusLabel.font = .systemFont(ofSize: NSFont.systemFontSize, weight: .medium)
        statusLabel.isHidden = true

        let header = NSStackView(views: [hostLabel, serverLabel, statusLabel])
        header.orientation = .vertical
        header.alignment = .leading
        header.spacing = 2
        header.edgeInsets = NSEdgeInsets(top: 8, left: 12, bottom: 8, right: 12)

        let stack = NSStackView(views: [header, webView])
        stack.orientation = .vertical
        stack.spacing = 0
        stack.alignment = .width
        window.contentView = stack
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    func load(_ url: URL) {
        hostLabel.stringValue = url.host ?? ""
        webView.load(URLRequest(url: url))
        window?.makeKeyAndOrderFront(nil)
    }

    func showStatus(_ text: String) {
        statusLabel.stringValue = text
        statusLabel.isHidden = false
        webView.isHidden = true
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        let isMainFrame = navigationAction.targetFrame?.isMainFrame ?? true
        switch CallbackCapture.decide(url, isMainFrame: isMainFrame) {
        case .allow:
            if isMainFrame { hostLabel.stringValue = url.host ?? "" }
            decisionHandler(.allow)
        case .cancel:
            decisionHandler(.cancel)
        case let .capture(callback):
            decisionHandler(.cancel)
            onCallback(callback)
        }
    }

    /// Links that would open a new window load here instead, under the same rules.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, CallbackCapture.decide(url, isMainFrame: true) == .allow {
            webView.load(navigationAction.request)
        }
        return nil
    }
}
