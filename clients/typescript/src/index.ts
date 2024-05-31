import { Base } from "@/resources/base";
import { GenTable } from "@/resources/gen_tables";
import { LLM } from "@/resources/llm";
import { applyMixins } from "@/utils";

class JamAI extends Base {}
interface JamAI extends GenTable, LLM {}

applyMixins(JamAI, [GenTable, LLM]);

export default JamAI;
