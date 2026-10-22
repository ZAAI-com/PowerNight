import Foundation

public enum NavigationDecision: Equatable {
    case allow
    case cancel
    /// Tesla's redirect to tesla://auth/callback; the value goes to PowerNight
    case capture(String)
}

/// Decides what the sign-in web view may load.
///
/// The main frame stays on Tesla's HTTPS sign-in pages. Embedded frames may
/// load other HTTPS content (Tesla uses third-party captcha frames). The
/// tesla:// redirect is never loaded: it is captured and handed to PowerNight.
public enum CallbackCapture {
    public static func decide(_ url: URL, isMainFrame: Bool) -> NavigationDecision {
        let scheme = url.scheme?.lowercased() ?? ""
        if scheme == "tesla" {
            return isTeslaCallback(url) ? .capture(url.absoluteString) : .cancel
        }
        if scheme == "about" {
            return .allow
        }
        guard scheme == "https", let host = url.host?.lowercased() else {
            return .cancel
        }
        if !isMainFrame {
            return .allow
        }
        return isTeslaHost(host) ? .allow : .cancel
    }

    public static func isTeslaCallback(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "tesla" && url.host?.lowercased() == "auth" && url.path == "/callback"
    }

    public static func isTeslaHost(_ host: String) -> Bool {
        ["tesla.com", "tesla.cn"].contains { host == $0 || host.hasSuffix("." + $0) }
    }
}
