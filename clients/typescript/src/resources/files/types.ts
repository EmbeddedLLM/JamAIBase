import { z } from "zod";

export const UploadFileRequestSchema = z.object({
    file: z
        .any()
        .optional(),
    file_path: z.string().optional()
});

export const UploadFileResponseSchema = z.object({
    object: z.literal("file.upload"),
    uri: z.string()
});

export const GetUrlRequestSchema = z.object({
    uris: z.array(z.string())
});
export const GetUrlResponseSchema = z.object({
    object: z.literal("file.urls"),
    urls: z.array(z.string())
});

export type IUploadFileRequest = z.input<typeof UploadFileRequestSchema>;
export type IUploadFileResponse = z.infer<typeof UploadFileResponseSchema>;

export type IGetUrlRequest = z.input<typeof GetUrlRequestSchema>;
export type IGetUrlResponse = z.infer<typeof GetUrlResponseSchema>;
