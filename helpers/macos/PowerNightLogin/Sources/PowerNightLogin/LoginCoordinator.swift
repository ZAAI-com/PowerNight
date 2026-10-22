import AppKit
import OSLog
import PowerNightLoginCore

private let log = Logger(subsystem: "com.zaai.powernight.login", category: "helper")

/// One sign-in: confirm the PowerNight server, fetch Tesla's sign-in page
/// for this attempt, capture the tesla:// result, and hand it to PowerNight.
///
/// PKCE, the token exchange, saving credentials and choosing the energy site
/// all stay on the PowerNight server. Nothing secret is logged or copied.
@MainActor
final class LoginCoordinator {
    private let request: LaunchRequest
    private let trustStore = TrustStore()
    private var client: HelperAPIClient?
    private var window: LoginWindowController?
    private var submitted = false

    init(request: LaunchRequest) {
        self.request = request
    }

    func start() {
        guard confirmServer() else {
            NSApp.terminate(nil)
            return
        }
        let client = HelperAPIClient(origin: request.origin, handoff: request.handoff)
        self.client = client
        let origin = request.origin
        let onCallback: (String) -> Void = { [weak self] callback in
            self?.submit(callback)
        }
        Task { @MainActor in
            do {
                let authorization = try await client.authorization()
                let signInURL = try AuthorizationURLValidator.validate(authorization.authURL)
                log.info("Opening Tesla sign-in")
                let window = LoginWindowController(origin: origin, onCallback: onCallback)
                self.window = window
                window.showWindow(nil)
                window.load(signInURL)
            } catch let error as HelperAPIError {
                Self.fail(error.userMessage)
            } catch {
                Self.fail("PowerNight did not provide a valid Tesla sign-in page.")
            }
        }
    }

    /// Unknown servers, and plain HTTP, always need an explicit confirmation.
    private func confirmServer() -> Bool {
        let origin = request.origin
        let trusted = trustStore.isTrusted(origin)
        let httpAllowed = trustStore.allowsHTTP(origin)

        switch OriginPolicy.evaluate(origin, httpAllowed: httpAllowed) {
        case let .rejected(reason):
            Self.fail(reason)
            return false
        case .allowed where trusted:
            return true
        case .allowed, .needsHTTPOptIn:
            break
        }

        let needsHTTP = origin.scheme == "http"
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "Sign in to Tesla for PowerNight at \(origin.absoluteString)?"
        alert.informativeText = "Only continue if you just clicked \"Sign In with the Mac Helper\" in PowerNight Settings "
            + "at this address. The Tesla sign-in result will be sent to this server."
        let httpCheckbox = NSButton(checkboxWithTitle: "Allow unencrypted HTTP for this local server", target: nil, action: nil)
        if needsHTTP {
            httpCheckbox.state = httpAllowed ? .on : .off
            alert.accessoryView = httpCheckbox
        }
        alert.addButton(withTitle: "Continue")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return false }

        let allowHTTP = needsHTTP && httpCheckbox.state == .on
        if needsHTTP && !allowHTTP {
            Self.fail("PowerNight at this address uses plain HTTP. Allow it for this local server, or use HTTPS.")
            return false
        }
        trustStore.trust(origin, allowHTTP: allowHTTP)
        return true
    }

    private func submit(_ callback: String) {
        guard !submitted, let client else { return }
        submitted = true
        window?.showStatus("Finishing sign-in with PowerNight...")
        Task { @MainActor in
            do {
                let result = try await client.submitCallback(callback)
                log.info("PowerNight accepted the Tesla sign-in result")
                if result.step == "selecting_site" || result.step == "complete" || result.step == "completing" {
                    Self.finish(
                        title: "Signed in to Tesla",
                        message: "Return to PowerNight in your browser to finish. If you have more than one energy site, choose it there."
                    )
                } else {
                    Self.finish(title: "Sign-in not finished", message: result.error ?? "Return to PowerNight and try again.")
                }
            } catch let error as HelperAPIError {
                Self.fail(error.userMessage)
            } catch {
                Self.fail("PowerNight did not accept the sign-in result.")
            }
        }
    }

    static func fail(_ message: String) {
        log.error("Sign-in stopped")
        finish(title: "PowerNight Login stopped", message: message, style: .warning)
    }

    private static func finish(title: String, message: String, style: NSAlert.Style = .informational) {
        let alert = NSAlert()
        alert.alertStyle = style
        alert.messageText = title
        alert.informativeText = message
        alert.runModal()
        NSApp.terminate(nil)
    }
}
