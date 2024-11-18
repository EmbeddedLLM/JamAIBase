import { IdSchema, TableSchemaCreateSchema } from "@/resources/gen_tables/tables";
import { z } from "zod";

export const CreateKnowledgeTableRequestSchema = TableSchemaCreateSchema.extend({
    embedding_model: z.string()
});
export type CreateKnowledgeTableRequest = z.input<typeof CreateKnowledgeTableRequestSchema>;

export const UploadFileRequestSchema = z.object({
    file: z
        .any()
        .refine((value) => value instanceof File, {
            message: "Value must be a File object"
        })
        .optional(),
    file_path: z.string().optional(),
    table_id: IdSchema,
    chunk_size: z.number().gt(0).optional(),
    chunk_overlap: z.number().min(0).optional()
});

export type UploadFileRequest = z.infer<typeof UploadFileRequestSchema>;
