<script lang="ts">
	import { Pagination as PaginationPrimitive } from 'bits-ui';

	type $$Props = PaginationPrimitive.PrevButtonProps;
	type $$Events = PaginationPrimitive.PrevButtonEvents;
</script>

<PaginationPrimitive.PrevButton asChild let:builder>
	<slot {builder} />
</PaginationPrimitive.PrevButton>
