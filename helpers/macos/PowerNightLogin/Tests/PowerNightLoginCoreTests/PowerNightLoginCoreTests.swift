import XCTest
@testable import PowerNightLoginCore

final class LaunchRequestTests: XCTestCase {
    private let handoff = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_xyz"

    private func link(_ query: String) -> URL {
        URL(string: "powernight-login://start?\(query)")!
    }

    func testParsesOriginAndHandoff() throws {
        let request = try LaunchRequest.parse(link("v=1&origin=https%3A%2F%2FNAS.local%3A8020&handoff=\(handoff)"))
        XCTAssertEqual(request.origin.absoluteString, "https://nas.local:8020")
        XCTAssertEqual(request.handoff, handoff)
    }

    func testDropsDefaultPorts() throws {
        let request = try LaunchRequest.parse(link("v=1&origin=https%3A%2F%2Fpowernight.example.com%3A443%2F&handoff=\(handoff)"))
        XCTAssertEqual(request.origin.absoluteString, "https://powernight.example.com")
    }

    func testRejectsOtherLinks() {
        XCTAssertThrowsError(try LaunchRequest.parse(URL(string: "https://start?v=1")!)) {
            XCTAssertEqual($0 as? LaunchRequest.ParseError, .notALaunchLink)
        }
        XCTAssertThrowsError(try LaunchRequest.parse(link("v=2&origin=https%3A%2F%2Fnas&handoff=\(handoff)"))) {
            XCTAssertEqual($0 as? LaunchRequest.ParseError, .unsupportedVersion)
        }
    }

    func testRejectsOriginsWithCredentialsPathsOrOtherSchemes() {
        for origin in [
            "https%3A%2F%2Fuser%3Apass%40nas.local",
            "https%3A%2F%2Fnas.local%2Fsettings",
            "https%3A%2F%2Fnas.local%3Fx%3D1",
            "file%3A%2F%2F%2Fetc",
            "javascript%3Aalert(1)",
        ] {
            XCTAssertThrowsError(try LaunchRequest.parse(link("v=1&origin=\(origin)&handoff=\(handoff)")), origin) {
                XCTAssertEqual($0 as? LaunchRequest.ParseError, .invalidOrigin)
            }
        }
    }

    func testRejectsMalformedHandoffs() {
        for value in ["", "short", String(repeating: "a", count: 200), "has%20space-and-is-long-enough"] {
            XCTAssertThrowsError(try LaunchRequest.parse(link("v=1&origin=https%3A%2F%2Fnas.local&handoff=\(value)")), value) {
                XCTAssertEqual($0 as? LaunchRequest.ParseError, .invalidHandoff)
            }
        }
    }
}

final class OriginPolicyTests: XCTestCase {
    func testHTTPSIsAllowed() {
        XCTAssertEqual(OriginPolicy.evaluate(URL(string: "https://powernight.example.com")!, httpAllowed: false), .allowed)
    }

    func testHTTPNeedsOptInOnLocalHosts() {
        for host in ["192.168.1.20", "10.0.0.5", "172.20.1.1", "169.254.3.4", "127.0.0.1", "nas.local", "nas", "localhost", "[fd00::5]", "[fe80::1]"] {
            let origin = URL(string: "http://\(host):8020")!
            XCTAssertEqual(OriginPolicy.evaluate(origin, httpAllowed: false), .needsHTTPOptIn, host)
            XCTAssertEqual(OriginPolicy.evaluate(origin, httpAllowed: true), .allowed, host)
        }
    }

    func testHTTPIsRejectedForPublicHosts() {
        for host in ["8.8.8.8", "172.32.0.1", "powernight.example.com", "[2001:db8::1]"] {
            let origin = URL(string: "http://\(host)")!
            guard case .rejected = OriginPolicy.evaluate(origin, httpAllowed: true) else {
                return XCTFail("HTTP to \(host) must be rejected even when opted in")
            }
        }
    }
}

final class TrustStoreTests: XCTestCase {
    func testRemembersConfirmedServersAndHTTPOptIn() throws {
        let suite = "PowerNightLoginTests-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = TrustStore(defaults: defaults)
        let origin = URL(string: "http://nas.local:8020")!

        XCTAssertFalse(store.isTrusted(origin))
        store.trust(origin, allowHTTP: true)
        XCTAssertTrue(store.isTrusted(URL(string: "http://NAS.local:8020/")!))
        XCTAssertTrue(store.allowsHTTP(origin))
        XCTAssertFalse(store.isTrusted(URL(string: "http://nas.local:8021")!))

        store.forget(origin)
        XCTAssertFalse(store.isTrusted(origin))
    }
}

final class AuthorizationURLValidatorTests: XCTestCase {
    private let valid = "https://auth.tesla.com/oauth2/v3/authorize?response_type=code&client_id=ownerapi"
        + "&redirect_uri=tesla%3A%2F%2Fauth%2Fcallback&scope=openid&state=abc&code_challenge=xyz"
        + "&code_challenge_method=S256&login_hint=owner%40example.com"

    func testAcceptsTeslaSignIn() throws {
        XCTAssertEqual(try AuthorizationURLValidator.validate(valid).host, "auth.tesla.com")
        XCTAssertNoThrow(try AuthorizationURLValidator.validate(valid.replacingOccurrences(of: "auth.tesla.com", with: "auth.tesla.cn")))
    }

    func testRejectsOtherHostsAndSchemes() {
        for url in [
            valid.replacingOccurrences(of: "auth.tesla.com", with: "auth.tesla.com.evil.example"),
            valid.replacingOccurrences(of: "https://", with: "http://"),
            valid.replacingOccurrences(of: "/oauth2/v3/authorize", with: "/login"),
            valid.replacingOccurrences(of: "auth.tesla.com", with: "user@auth.tesla.com"),
        ] {
            XCTAssertThrowsError(try AuthorizationURLValidator.validate(url), url) {
                XCTAssertEqual($0 as? AuthorizationURLValidator.ValidationError, .notTeslaSignIn)
            }
        }
    }

    func testRequiresPKCEAndTheTeslaRedirect() {
        XCTAssertThrowsError(try AuthorizationURLValidator.validate(valid.replacingOccurrences(of: "&code_challenge_method=S256", with: "")))
        XCTAssertThrowsError(try AuthorizationURLValidator.validate(valid.replacingOccurrences(of: "tesla%3A%2F%2Fauth%2Fcallback", with: "https%3A%2F%2Fevil.example")))
        XCTAssertThrowsError(try AuthorizationURLValidator.validate(valid.replacingOccurrences(of: "client_id=ownerapi", with: "client_id=other")))
        XCTAssertThrowsError(try AuthorizationURLValidator.validate(valid.replacingOccurrences(of: "state=abc", with: "state=")))
    }
}

final class CallbackCaptureTests: XCTestCase {
    func testCapturesTheTeslaCallback() {
        let url = URL(string: "tesla://auth/callback?code=c1&state=s1&issuer=https%3A%2F%2Fauth.tesla.com")!
        XCTAssertEqual(CallbackCapture.decide(url, isMainFrame: true), .capture(url.absoluteString))
        XCTAssertEqual(CallbackCapture.decide(URL(string: "tesla://other/thing")!, isMainFrame: true), .cancel)
    }

    func testKeepsTheMainFrameOnTesla() {
        XCTAssertEqual(CallbackCapture.decide(URL(string: "https://auth.tesla.com/oauth2/v3/authorize")!, isMainFrame: true), .allow)
        XCTAssertEqual(CallbackCapture.decide(URL(string: "https://www.tesla.com/support")!, isMainFrame: true), .allow)
        XCTAssertEqual(CallbackCapture.decide(URL(string: "https://evil.example/tesla.com")!, isMainFrame: true), .cancel)
        XCTAssertEqual(CallbackCapture.decide(URL(string: "https://faketesla.com")!, isMainFrame: true), .cancel)
        XCTAssertEqual(CallbackCapture.decide(URL(string: "http://auth.tesla.com")!, isMainFrame: true), .cancel)
    }

    func testAllowsHTTPSFramesForCaptcha() {
        XCTAssertEqual(CallbackCapture.decide(URL(string: "https://hcaptcha.com/checkbox")!, isMainFrame: false), .allow)
        XCTAssertEqual(CallbackCapture.decide(URL(string: "http://hcaptcha.com/checkbox")!, isMainFrame: false), .cancel)
    }
}

final class HelperAPIClientTests: XCTestCase {
    func testRequestsCarryTheHandoffOnlyInAHeader() throws {
        let client = HelperAPIClient(origin: URL(string: "https://nas.local:8020")!, handoff: "handoff-value-1234567890")
        let request = client.makeRequest(path: "api/auth/setup/helper/callback", method: "POST", body: ["callback_url": "tesla://auth/callback?code=a&state=b"])

        XCTAssertEqual(request.url?.absoluteString, "https://nas.local:8020/api/auth/setup/helper/callback")
        XCTAssertEqual(request.value(forHTTPHeaderField: HelperAPIClient.handoffHeader), "handoff-value-1234567890")
        XCTAssertFalse(request.url!.absoluteString.contains("handoff"))
        let body = try XCTUnwrap(request.httpBody)
        XCTAssertEqual(try JSONSerialization.jsonObject(with: body) as? [String: String], ["callback_url": "tesla://auth/callback?code=a&state=b"])
    }

    func testRefusesEveryRedirect() {
        let client = HelperAPIClient(origin: URL(string: "https://nas.local")!, handoff: "handoff-value-1234567890")
        let task = URLSession.shared.dataTask(with: URL(string: "https://nas.local/api")!)
        let response = HTTPURLResponse(url: URL(string: "https://nas.local/api")!, statusCode: 302, httpVersion: nil,
                                       headerFields: ["Location": "https://evil.example/api"])!
        let followed = expectation(description: "redirect decision")
        client.urlSession(URLSession.shared, task: task, willPerformHTTPRedirection: response,
                          newRequest: URLRequest(url: URL(string: "https://evil.example/api")!)) { request in
            XCTAssertNil(request)
            followed.fulfill()
        }
        wait(for: [followed], timeout: 1)
    }
}
