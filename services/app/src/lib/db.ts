import Dexie, { type EntityTable } from 'dexie';

interface Table {
	id: string;
	columns: Record<string, number>;
}

export const db = new Dexie('jamai') as Dexie & {
	action_table: EntityTable<Table, 'id'>;
	knowledge_table: EntityTable<Table, 'id'>;
	chat_table: EntityTable<Table, 'id'>;
};
db.version(1).stores({
	action_table: 'id, columns',
	knowledge_table: 'id, columns',
	chat_table: 'id, columns'
});
