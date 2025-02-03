<script lang="ts">
	import { Pagination as PaginationPrimitive } from 'bits-ui';

	type $$Props = PaginationPrimitive.NextButtonProps;
	type $$Events = PaginationPrimitive.NextButtonEvents;
</script>

<PaginationPrimitive.NextButton asChild let:builder>
	<slot {builder} />
</PaginationPrimitive.NextButton>
