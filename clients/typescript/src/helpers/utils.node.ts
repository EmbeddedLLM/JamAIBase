export const getFileName = async (filePath: string) => {
    if (typeof window === "undefined") {
        const path = await import("path");
        return path?.basename(filePath!);
    }
    return "";
};

export const readFile = async (filePath: string) => {
    if (typeof window === "undefined") {
        const { promises: fs } = await import("fs");
        return await fs?.readFile(filePath!);
    }
    return "";
};

export const getMimeType = async (filePath: string) => {
    if (typeof window === "undefined") {
        const mime = await import("mime-types");
        return mime?.lookup(filePath!) || "application/octet-stream";
    }
    return "";
};

export const getOSInfoNode = async () => {
    if (typeof window === "undefined") {
        const os = await import("os");
        const platform = os?.platform() || "";
        const arch = os?.arch();
        let osName = "Unknown OS";

        switch (platform) {
            case "win32":
                osName = "Windows";
                break;
            case "darwin":
                osName = "macOS";
                break;
            case "linux":
                osName = "Linux";
                break;
            default:
                osName = platform;
        }

        return `${osName} ${os?.release()}; ${arch}`;
    }
    return "";
};
