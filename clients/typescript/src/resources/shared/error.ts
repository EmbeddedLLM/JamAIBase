export class ChunkError extends Error {
    type: string = "ChunkError";

    constructor(message?: string) {
        super(message);
        this.name = this.constructor.name;
        this.message = message || "";
        Error.captureStackTrace(this, this.constructor); // Capture stack trace
    }

    override toString(): string {
        return `[${this.type} -  ${this.message}`;
    }
}
