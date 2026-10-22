import Foundation

/// Accept only a genuine Tesla sign-in URL for the owner API client.
///
/// The server hands this URL to the helper, so the helper checks it: it must
/// be Tesla's own page with PKCE and the tesla:// redirect, never anything
/// else a server might send.
public enum AuthorizationURLValidator {
    public static let allowedHosts: Set<String> = ["auth.tesla.com", "auth.tesla.cn"]

    public enum ValidationError: Error, Equatable {
        case notTeslaSignIn
        case missingParameter(String)
        case unexpectedParameter(String)
    }

    public static func validate(_ text: String) throws -> URL {
        guard let components = URLComponents(string: text),
              components.scheme?.lowercased() == "https",
              let host = components.host?.lowercased(), allowedHosts.contains(host),
              components.port == nil || components.port == 443,
              components.user == nil, components.password == nil,
              components.path == "/oauth2/v3/authorize",
              let url = components.url else {
            throw ValidationError.notTeslaSignIn
        }
        let items = components.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }

        let expected = [
            "client_id": "ownerapi",
            "redirect_uri": "tesla://auth/callback",
            "response_type": "code",
            "code_challenge_method": "S256",
        ]
        for (name, required) in expected {
            guard let actual = value(name) else { throw ValidationError.missingParameter(name) }
            guard actual == required else { throw ValidationError.unexpectedParameter(name) }
        }
        for name in ["state", "code_challenge"] {
            guard let actual = value(name), !actual.isEmpty else { throw ValidationError.missingParameter(name) }
        }
        return url
    }
}
