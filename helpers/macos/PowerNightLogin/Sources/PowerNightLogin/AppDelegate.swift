import AppKit
import PowerNightLoginCore

/// Receives `powernight-login://start` links from PowerNight Settings.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var coordinator: LoginCoordinator?
    private var openedWithLink = false

    func applicationWillFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = Self.makeMainMenu()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Give a launch link a moment to arrive before explaining how to start
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            guard let self, !self.openedWithLink else { return }
            let alert = NSAlert()
            alert.messageText = "Start PowerNight Login from PowerNight"
            alert.informativeText = "Open PowerNight Settings in your browser, start the Tesla sign-in, and choose "
                + "\"Sign In with the Mac Helper\". This app then opens Tesla sign-in for you."
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard let url = urls.first else { return }
        openedWithLink = true
        NSApp.activate(ignoringOtherApps: true)
        do {
            let request = try LaunchRequest.parse(url)
            let coordinator = LoginCoordinator(request: request)
            self.coordinator = coordinator
            coordinator.start()
        } catch {
            LoginCoordinator.fail("This PowerNight Login link is not valid. Start the sign-in again from PowerNight Settings.")
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    /// App and Edit menus, so Cmd+Q and Cmd+V (password managers) work in the web view.
    private static func makeMainMenu() -> NSMenu {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit PowerNight Login", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        main.addItem(editItem)
        return main
    }
}
