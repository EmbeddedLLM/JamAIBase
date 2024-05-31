import { TableSchemaCreateSchema } from "@/resources/gen_tables/tables";
import { z } from "zod";

export const CreateActionTableRequestSchema = TableSchemaCreateSchema;
export const AddActionColumnRequestSchema = TableSchemaCreateSchema;
export type CreateActionTableRequest = z.infer<typeof CreateActionTableRequestSchema>;
export type AddActionColumnRequest = z.infer<typeof AddActionColumnRequestSchema>;
