class BillingManager:
    def __init__(self, *args, **kwargs) -> None:
        pass

    @property
    def total_balance(self) -> float:
        return 0.0

    async def process_all(self, *args, **kwargs) -> None:
        return

    # --- LLM Usage --- #

    def check_llm_quota(self, *args, **kwargs) -> None:
        return

    def check_gen_table_llm_quota(self, *args, **kwargs):
        return

    def create_llm_events(self, *args, **kwargs):
        return

    async def process_llm_usage(self) -> None:
        return

    # --- Egress Usage --- #

    def check_egress_quota(self, *args, **kwargs) -> None:
        return

    def create_egress_events(self, *args, **kwargs):
        return

    async def process_egress_usage(self, *args, **kwargs) -> None:
        return

    # --- Storage Usage --- #

    def check_db_storage_quota(self) -> None:
        return

    def check_file_storage_quota(self) -> None:
        return

    def get_storage_usage(self):
        return

    async def process_storage_usage(self):
        return
