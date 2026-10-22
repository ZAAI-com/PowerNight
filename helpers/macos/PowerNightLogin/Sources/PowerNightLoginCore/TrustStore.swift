import Foundation

/// PowerNight servers the user confirmed once (trust on first use).
///
/// Without this, any web page could open a launch link naming its own
/// server, have the user sign in to the real Tesla page, and receive the
/// sign-in result. Unknown servers therefore always need an explicit "yes".
public final class TrustStore {
    private let defaults: UserDefaults
    private let key = "trustedPowerNightOrigins"

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    private var entries: [String: [String: Bool]] {
        get { defaults.dictionary(forKey: key) as? [String: [String: Bool]] ?? [:] }
        set { defaults.set(newValue, forKey: key) }
    }

    public func isTrusted(_ origin: URL) -> Bool {
        entries[Origin.key(origin)] != nil
    }

    public func allowsHTTP(_ origin: URL) -> Bool {
        entries[Origin.key(origin)]?["allowHTTP"] ?? false
    }

    public func trust(_ origin: URL, allowHTTP: Bool) {
        var current = entries
        current[Origin.key(origin)] = ["allowHTTP": allowHTTP]
        entries = current
    }

    public func forget(_ origin: URL) {
        var current = entries
        current.removeValue(forKey: Origin.key(origin))
        entries = current
    }
}
