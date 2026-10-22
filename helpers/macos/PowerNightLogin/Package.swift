// swift-tools-version:5.9
import PackageDescription

// Experimental macOS helper for PowerNight's Tesla sign-in. The logic that
// decides what is trusted lives in PowerNightLoginCore so it can be tested
// without a window; PowerNightLogin is the AppKit/WebKit shell around it.
let package = Package(
    name: "PowerNightLogin",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "PowerNightLogin", targets: ["PowerNightLogin"]),
    ],
    targets: [
        .target(name: "PowerNightLoginCore"),
        .executableTarget(name: "PowerNightLogin", dependencies: ["PowerNightLoginCore"]),
        .testTarget(name: "PowerNightLoginCoreTests", dependencies: ["PowerNightLoginCore"]),
    ]
)
