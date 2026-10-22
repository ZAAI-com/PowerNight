import Foundation

public struct HelperAuthorization: Decodable, Equatable {
    public let authURL: String
    public let email: String?
    public let setupExpiresInSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case authURL = "auth_url"
        case email
        case setupExpiresInSeconds = "setup_expires_in_seconds"
    }
}

public struct HelperCallbackResult: Decodable, Equatable {
    public let success: Bool
    public let step: String?
    public let errorCode: String?
    public let error: String?

    enum CodingKeys: String, CodingKey {
        case success, step, error
        case errorCode = "error_code"
    }
}

public enum HelperAPIError: Error, Equatable {
    /// PowerNight answered with an error; `message` is safe to show
    case server(status: Int, code: String?, message: String)
    case redirectRefused
    case invalidResponse
    case unreachable(String)

    public var userMessage: String {
        switch self {
        case let .server(_, _, message): return message
        case .redirectRefused: return "PowerNight answered with a redirect to another address, so the helper stopped."
        case .invalidResponse: return "PowerNight sent an unexpected answer."
        case let .unreachable(reason): return "PowerNight could not be reached: \(reason)"
        }
    }
}

private struct ErrorBody: Decodable {
    let errorCode: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case error
        case errorCode = "error_code"
    }
}

/// Talks to the two helper endpoints of one PowerNight server.
///
/// Uses an ephemeral session (no cookies or cache), refuses every redirect so
/// the destination can never change, and keeps the system's certificate
/// checks. The handoff travels only in a request header.
public final class HelperAPIClient: NSObject, URLSessionTaskDelegate {
    public static let handoffHeader = "X-PowerNight-Handoff"

    private let origin: URL
    private let handoff: String
    private lazy var session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)

    public init(origin: URL, handoff: String) {
        self.origin = origin
        self.handoff = handoff
    }

    func makeRequest(path: String, method: String, body: [String: String]? = nil) -> URLRequest {
        var request = URLRequest(url: origin.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(handoff, forHTTPHeaderField: Self.handoffHeader)
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        return request
    }

    public func authorization() async throws -> HelperAuthorization {
        try await send(makeRequest(path: "api/auth/setup/helper/authorization", method: "GET"))
    }

    public func submitCallback(_ callback: String) async throws -> HelperCallbackResult {
        try await send(makeRequest(path: "api/auth/setup/helper/callback", method: "POST", body: ["callback_url": callback]))
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw HelperAPIError.unreachable(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else { throw HelperAPIError.invalidResponse }
        if (300..<400).contains(http.statusCode) { throw HelperAPIError.redirectRefused }
        guard (200..<300).contains(http.statusCode) else {
            let body = try? JSONDecoder().decode(ErrorBody.self, from: data)
            throw HelperAPIError.server(
                status: http.statusCode,
                code: body?.errorCode,
                message: body?.error ?? "PowerNight answered with HTTP \(http.statusCode)."
            )
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw HelperAPIError.invalidResponse
        }
    }

    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           willPerformHTTPRedirection response: HTTPURLResponse,
                           newRequest request: URLRequest,
                           completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
