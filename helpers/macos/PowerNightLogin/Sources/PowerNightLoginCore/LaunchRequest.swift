import Foundation

/// A `powernight-login://start` link opened from PowerNight Settings.
///
/// It carries only the PowerNight address and a short-lived handoff bound to
/// one sign-in attempt; never the PowerNight API key or a Tesla token.
public struct LaunchRequest: Equatable {
    public let origin: URL
    public let handoff: String

    public enum ParseError: Error, Equatable {
        case notALaunchLink
        case unsupportedVersion
        case invalidOrigin
        case invalidHandoff
    }

    public static let scheme = "powernight-login"
    private static let handoffCharacters = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )

    public static func parse(_ url: URL) throws -> LaunchRequest {
        guard url.scheme?.lowercased() == scheme, url.host?.lowercased() == "start" else {
            throw ParseError.notALaunchLink
        }
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }

        guard value("v") == "1" else { throw ParseError.unsupportedVersion }
        guard let originText = value("origin"), let origin = Origin.normalize(originText) else {
            throw ParseError.invalidOrigin
        }
        guard let handoff = value("handoff"),
              (20...128).contains(handoff.count),
              handoff.unicodeScalars.allSatisfy(handoffCharacters.contains) else {
            throw ParseError.invalidHandoff
        }
        return LaunchRequest(origin: origin, handoff: handoff)
    }
}

/// Origins are compared and stored as `scheme://host[:port]`, nothing else.
public enum Origin {
    public static func normalize(_ text: String) -> URL? {
        guard let components = URLComponents(string: text),
              let scheme = components.scheme?.lowercased(), scheme == "https" || scheme == "http",
              let host = components.host?.lowercased(), !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              components.path.isEmpty || components.path == "/" else {
            return nil
        }
        var normalized = URLComponents()
        normalized.scheme = scheme
        normalized.host = host
        if let port = components.port, port != (scheme == "https" ? 443 : 80) {
            normalized.port = port
        }
        return normalized.url
    }

    public static func key(_ origin: URL) -> String {
        Origin.normalize(origin.absoluteString)?.absoluteString ?? origin.absoluteString
    }
}
