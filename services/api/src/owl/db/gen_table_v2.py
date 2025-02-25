from typing import Self

import numpy as np


class GenerativeTableCore:
    ### --- Table CRUD --- ###

    # Create
    @classmethod
    async def create_table(cls, table_id: str) -> Self:
        pass

    @classmethod
    async def duplicate_table(cls, table_id: str) -> Self:
        pass

    # Read
    @classmethod
    async def list_tables(cls, table_id: str) -> list[Self]:
        pass

    @classmethod
    async def get_table(cls, table_id: str) -> Self:
        pass

    async def count_rows(self):
        pass

    # Update
    async def rename_table(self):
        pass

    async def recreate_fts_index(self):
        # Optional
        pass

    async def recreate_vector_index(self):
        # Optional
        pass

    async def drop_fts_index(self):
        # Optional
        pass

    async def drop_vector_index(self):
        # Optional
        pass

    # Delete
    async def drop_table(self):
        pass

    # Import Export
    async def export_table(self):
        pass

    async def import_table(self):
        pass

    async def export_data(self):
        pass

    async def import_data(self):
        pass

    ### --- Column CRUD --- ###

    # Create
    async def add_column(self):
        pass

    # Read ops are implemented as table ops
    # Update
    async def update_gen_config(self):
        pass

    async def rename_column(self):
        pass

    async def reorder_columns(self):
        # Need to ensure that length of new order list matches the number of columns
        pass

    # Delete
    async def drop_column(self):
        pass

    ### --- Row CRUD --- ###

    # Create
    async def add_row(self):
        pass

    async def add_rows(self):
        # Optional, if batch operation is supported
        pass

    # Read
    async def list_rows(self):
        pass

    async def get_row(self):
        pass

    async def fts_search(self, query: str):
        pass

    async def vector_search(self, query: list[float] | np.ndarray):
        pass

    # Update
    async def update_row(self):
        pass

    async def update_rows(self):
        # Optional, if batch operation is supported
        pass

    # Delete
    async def delete_row(self):
        pass

    async def delete_rows(self):
        # Optional, if batch operation is supported
        pass
