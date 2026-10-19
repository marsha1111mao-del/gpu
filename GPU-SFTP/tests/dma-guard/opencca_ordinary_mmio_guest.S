	.section .rodata
	.balign 16
	.global ordinary_mmio_guest_start
	.global ordinary_mmio_guest_end
	.type ordinary_mmio_guest_start, %object
ordinary_mmio_guest_start:
	ldr w2, [x0, #0x34]
	tst w2, #3
	b.ne .Lexit
	ldr w3, [x0, #0x20]
	tst w3, #1
	b.ne .Lexit
	ldr w4, [x0, #0x28]
	eor w5, w4, #1
	str w5, [x0, #0x28]
	dsb sy
	ldr w6, [x0, #0x28]
	str w4, [x0, #0x28]
	dsb sy
	ldr w7, [x0, #0x28]
	stp w4, w5, [x1]
	stp w6, w7, [x1, #8]
	mov w8, #1
	str w8, [x1, #16]
.Lexit:
	mov x9, #0x10000000
	mov w10, #0x4d4d
	str w10, [x9]
	b .
ordinary_mmio_guest_end:
	.size ordinary_mmio_guest_start, .-ordinary_mmio_guest_start
	.section .note.GNU-stack,"",%progbits
