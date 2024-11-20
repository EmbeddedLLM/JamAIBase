export const getOSInfoBrwoser = () => {
    const userAgent = window.navigator.userAgent;
    const platform = window.navigator.platform;
    const architecture = window.navigator.userAgent.includes("WOW64") || window.navigator.userAgent.includes("Win64") ? "x64" : "x86";

    let browser = "Unknown";

    if (userAgent.includes("Firefox")) {
        browser = "Firefox";
    } else if (userAgent.includes("Chrome")) {
        browser = "Chrome";
    } else if (userAgent.includes("Safari")) {
        browser = "Safari";
    } else if (userAgent.includes("Edge")) {
        browser = "Edge";
    } else if (userAgent.includes("Opera") || userAgent.includes("OPR")) {
        browser = "Opera";
    }

    let os = "Unknown OS";
    if (platform?.startsWith("Win")) {
        os = "Windows";
    } else if (platform?.startsWith("Mac")) {
        os = "macOS";
    } else if (platform?.startsWith("Linux")) {
        os = "Linux";
    } else if (/Android/.test(userAgent)) {
        os = "Android";
    } else if (/iPhone|iPad|iPod/.test(userAgent)) {
        os = "iOS";
    }

    return `${browser}-${os}; ${architecture}`;
};
