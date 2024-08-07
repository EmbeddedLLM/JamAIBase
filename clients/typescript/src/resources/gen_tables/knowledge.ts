import { IdSchema, TableSchemaCreateSchema } from "@/resources/gen_tables/tables";
import { z } from "zod";
import { zfd } from "zod-form-data";

export const CreateKnowledgeTableRequestSchema = TableSchemaCreateSchema.extend({
    embedding_model: z.string()
});
export type CreateKnowledgeTableRequest = z.infer<typeof CreateKnowledgeTableRequestSchema>;

export const UploadFileRequestSchema = zfd.formData({
    file: zfd.file().optional(),
    file_path: zfd.text().optional(),
    table_id: zfd.text(IdSchema),
    chunk_size: zfd.numeric(z.number().gt(0)).optional(),
    chunk_overlap: zfd.numeric(z.number().min(0)).optional()
});

export type UploadFileRequest = z.infer<typeof UploadFileRequestSchema>;
