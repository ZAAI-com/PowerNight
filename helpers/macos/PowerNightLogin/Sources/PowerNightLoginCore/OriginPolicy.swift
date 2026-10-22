import Foundation

public enum OriginDecision: Equatable {
    case allowed
    /// Plain HTTP to a local server: allowed only after the user opts in for that server
    case needsHTTPOptIn
    case rejected(String)
}

/// HTTPS by default; HTTP only for servers on the local network, and only
/// after an explicit opt-in stored by the helper (never taken from the link).
public enum OriginPolicy {
    public static func evaluate(_ origin: URL, httpAllowed: Bool) -> OriginDecision {
        switch origin.scheme?.lowercased() {
        case "https":
            return .allowed
        case "http":
            guard let host = origin.host, isLocalHost(host) else {
                return .rejected("PowerNight must use HTTPS unless it runs on your local network.")
            }
            return httpAllowed ? .allowed : .needsHTTPOptIn
        default:
            return .rejected("This is not a PowerNight web address.")
        }
    }

    /// Hosts App Transport Security treats as local: private and link-local
    /// addresses, loopback, `.local` names and single-label names.
    public static func isLocalHost(_ rawHost: String) -> Bool {
        let host = rawHost.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).lowercased()
        if host == "localhost" || host.hasSuffix(".local") { return true }
        if let octets = ipv4Octets(host) {
            switch (octets[0], octets[1]) {
            case (10, _), (127, _), (192, 168), (169, 254): return true
            case (172, 16...31): return true
            default: return false
            }
        }
        if host.contains(":") {
            return host == "::1" || host.hasPrefix("fc") || host.hasPrefix("fd")
                || host.hasPrefix("fe8") || host.hasPrefix("fe9") || host.hasPrefix("fea") || host.hasPrefix("feb")
        }
        return !host.contains(".") && !host.isEmpty
    }

    private static func ipv4Octets(_ host: String) -> [Int]? {
        let parts = host.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return nil }
        let octets = parts.compactMap { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) else { return nil }
        return octets
    }
}
