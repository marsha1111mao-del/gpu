struct isolation_context {
	struct drm_panthor_vm_create vm;
	struct drm_panthor_bo_create bo;
	struct drm_panthor_group_create group;
	struct drm_syncobj_create sync;
	volatile uint32_t *mapping;
};

static int isolation_bind(int fd, uint32_t vm, uint32_t bo, uint64_t va,
			  uint64_t offset, uint64_t size, uint32_t flags)
{
	struct drm_panthor_vm_bind_op op = {
		.flags = flags, .bo_handle = bo, .va = va,
		.bo_offset = offset, .size = size,
	};
	struct drm_panthor_vm_bind bind = {
		.vm_id = vm,
		.ops = { .count = 1, .stride = sizeof(op),
			 .array = (uint64_t)(uintptr_t)&op },
	};

	return ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind);
}

static int isolation_rejected(const char *name, int result, int expected)
{
	if (result != -1 || errno != expected) {
		fprintf(stderr, "GPUVM_ISOLATION %s result=%d errno=%d expected=%d\n",
			name, result, errno, expected);
		return -1;
	}
	printf("GPUVM_ISOLATION %s=PASS errno=%d\n", name, errno);
	return 0;
}

static int isolation_submit(int fd, const struct isolation_context *context,
			    bool expect_fault)
{
	struct drm_panthor_sync_op signal = {
		.handle = context->sync.handle,
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL |
			 DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ,
	};
	struct drm_panthor_queue_submit job = {
		.stream_addr = 0x400000, .stream_size = 96,
		.syncs = { .count = 1, .stride = sizeof(signal),
			   .array = (uint64_t)(uintptr_t)&signal },
	};
	struct drm_panthor_group_submit submit = {
		.group_handle = context->group.group_handle,
		.queue_submits = { .count = 1, .stride = sizeof(job),
				   .array = (uint64_t)(uintptr_t)&job },
	};
	struct drm_syncobj_array reset = {
		.handles = (uint64_t)(uintptr_t)&context->sync.handle,
		.count_handles = 1,
	};
	struct drm_syncobj_wait wait = {
		.handles = reset.handles, .count_handles = 1,
		.flags = DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL |
			 DRM_SYNCOBJ_WAIT_FLAGS_WAIT_FOR_SUBMIT,
		.timeout_nsec = abs_timeout_after_ns(5000000000LL),
	};
	struct drm_syncobj_handle exported = {
		.handle = context->sync.handle,
		.flags = DRM_SYNCOBJ_HANDLE_TO_FD_FLAGS_EXPORT_SYNC_FILE,
		.fd = -1,
	};
	struct sync_file_info info = { 0 };
	struct pollfd pollfd;
	int ret;

	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_RESET, &reset) ||
	    ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_SUBMIT, &submit) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) ||
	    ioctl(fd, DRM_IOCTL_SYNCOBJ_HANDLE_TO_FD, &exported))
		return -1;
	pollfd = (struct pollfd){ .fd = exported.fd, .events = POLLIN };
	ret = poll(&pollfd, 1, 5000);
	if (ret == 1)
		ret = ioctl(exported.fd, SYNC_IOC_FILE_INFO, &info);
	else
		ret = -1;
	close(exported.fd);
	if (ret || (expect_fault ? info.status >= 0 : info.status != 1)) {
		fprintf(stderr, "GPUVM_ISOLATION fence status=%d\n", info.status);
		return -1;
	}
	return 0;
}

static int gpuvm_isolation_check(int fd, const char *path, bool inject_fault)
{
	struct isolation_context contexts[2] = { 0 };
	struct drm_panthor_gpu_info gpu = { 0 };
	struct drm_panthor_queue_create queue = { .ringbuf_size = 4096 };
	struct drm_panthor_vm_create foreign_vm = { 0 };
	struct drm_panthor_vm_destroy destroy = { 0 };
	struct drm_panthor_group_destroy group_destroy = { 0 };
	struct drm_panthor_group_create duplicate;
	uint32_t expected[2] = { 0x71aabbcc, 0x82ddeeff };
	uint32_t readback[2] = { 0, 0 };
	uint32_t old_vm;
	unsigned int index, round;
	int other_fd = -1, ret = -1;

	if (query_gpu_info_out(fd, &gpu))
		return -1;
	for (index = 0; index < ARRAY_SIZE(contexts); index++) {
		struct isolation_context *context = &contexts[index];
		struct drm_panthor_bo_mmap_offset offset = { 0 };
		uint64_t *stream;

		context->vm.flags = DRM_PANTHOR_VM_CREATE_ISOLATED;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &context->vm))
			goto out;
		context->bo.size = 8192;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &context->bo))
			goto out;
		offset.handle = context->bo.handle;
		if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET, &offset))
			goto out;
		context->mapping = mmap(NULL, 8192, PROT_READ | PROT_WRITE,
					 MAP_SHARED, fd, offset.offset);
		if (context->mapping == MAP_FAILED) {
			context->mapping = NULL;
			goto out;
		}
		stream = (uint64_t *)context->mapping;
		stream[0] = (1ULL << 56) | (8ULL << 48) | 0x401000;
		stream[1] = (20ULL << 56) | (10ULL << 48) | (8ULL << 40) | (1ULL << 16);
		stream[2] = (3ULL << 56) | (0xffULL << 16);
		stream[3] = (1ULL << 56) | (12ULL << 48) | 0x401004;
		stream[4] = (21ULL << 56) | (10ULL << 48) | (12ULL << 40) | (1ULL << 16);
		stream[5] = (3ULL << 56) | (0xffULL << 16);
		stream[6] = (2ULL << 56) | (10ULL << 48) | (0x11220000 + index);
		stream[7] = (21ULL << 56) | (10ULL << 48) | (8ULL << 40) | (1ULL << 16);
		stream[8] = (3ULL << 56) | (0xffULL << 16);
		stream[9] = (2ULL << 56) | (14ULL << 48);
		stream[10] = (36ULL << 56) | (14ULL << 40) | 0x233;
		stream[11] = (3ULL << 56) | (1ULL << 16);
		context->mapping[1024] = expected[index];
		context->mapping[1025] = 0;
		__sync_synchronize();
		if (isolation_bind(fd, context->vm.id, context->bo.handle,
				   0x400000, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP))
			goto out;
		context->group = (struct drm_panthor_group_create){
			.vm_id = context->vm.id,
			.queues = { .count = 1, .stride = sizeof(queue),
				    .array = (uint64_t)(uintptr_t)&queue },
			.max_compute_cores = 1, .max_fragment_cores = 1, .max_tiler_cores = 1,
			.compute_core_mask = first_bit_mask64(gpu.shader_present),
			.fragment_core_mask = first_bit_mask64(gpu.shader_present),
			.tiler_core_mask = first_bit_mask64(gpu.tiler_present),
		};
		if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &context->group) ||
		    ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &context->sync))
			goto out;
	}
	duplicate = contexts[0].group;
	if (isolation_rejected("second_group",
		ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &duplicate), EACCES))
		goto out;
	destroy.id = contexts[0].vm.id;
	if (isolation_rejected("active_root_replace",
		ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy), EBUSY))
		goto out;
	if (isolation_rejected("cross_gpuvm_map",
		isolation_bind(fd, contexts[1].vm.id, contexts[0].bo.handle,
			0x800000, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EACCES) ||
	    isolation_rejected("readonly_cross_gpuvm_alias",
		isolation_bind(fd, contexts[1].vm.id, contexts[0].bo.handle,
			0x800000, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP |
			DRM_PANTHOR_VM_BIND_OP_MAP_READONLY), EACCES))
		goto out;
	if (isolation_bind(fd, contexts[0].vm.id, contexts[0].bo.handle,
		0x800000, 4096, 4096, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP |
		DRM_PANTHOR_VM_BIND_OP_MAP_READONLY | DRM_PANTHOR_VM_BIND_OP_MAP_NOEXEC) ||
	    isolation_bind(fd, contexts[0].vm.id, 0,
		0x800000, 0, 4096, DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP))
		goto out;
	printf("GPUVM_ISOLATION same_domain_readonly_alias=PASS\n");
	if (isolation_rejected("bo_bounds",
		isolation_bind(fd, contexts[0].vm.id, contexts[0].bo.handle,
			0x800000, 8192, 4096, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EINVAL) ||
	    isolation_rejected("reserved_va",
		isolation_bind(fd, contexts[0].vm.id, contexts[0].bo.handle,
			contexts[0].vm.user_va_range, 0, 4096,
			DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EINVAL))
		goto out;
	if (isolation_rejected("reserved_va_unmap",
		isolation_bind(fd, contexts[0].vm.id, 0,
			contexts[0].vm.user_va_range, 0, 4096,
			DRM_PANTHOR_VM_BIND_OP_TYPE_UNMAP), EINVAL) ||
	    isolation_rejected("wrapped_va",
		isolation_bind(fd, contexts[0].vm.id, contexts[0].bo.handle,
			UINT64_MAX - 4095, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EINVAL))
		goto out;
	other_fd = open(path, O_RDWR | O_CLOEXEC);
	if (other_fd < 0 || ioctl(other_fd, DRM_IOCTL_PANTHOR_VM_CREATE, &foreign_vm))
		goto out;
	if (isolation_rejected("foreign_session_bo",
		isolation_bind(other_fd, foreign_vm.id, contexts[0].bo.handle,
			0x400000, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EINVAL))
		goto out;
	for (round = 0; round < 32; round++) {
		index = round % 2;
		if (isolation_submit(fd, &contexts[index], false))
			goto out;
		readback[index] = expected[index];
		expected[index] = 0x11220000 + index;
		__sync_synchronize();
		if (contexts[0].mapping[1024] != expected[0] ||
		    contexts[1].mapping[1024] != expected[1] ||
		    contexts[0].mapping[1025] != readback[0] ||
		    contexts[1].mapping[1025] != readback[1]) {
			fprintf(stderr, "GPUVM_ISOLATION canary round=%u actual=%x/%x expected=%x/%x\n",
				round, contexts[0].mapping[1024], contexts[1].mapping[1024],
				expected[0], expected[1]);
			goto out;
		}
	}
	printf("GPUVM_ISOLATION actual_gpu_load_store=PASS groups=2 same_va=0x401000 switches=32 canaries=preserved fences=success\n");
	if (inject_fault) {
		struct drm_panthor_group_get_state state = {
			.group_handle = contexts[0].group.group_handle,
		};
		uint64_t *stream = (uint64_t *)contexts[0].mapping;

		if (isolation_bind(fd, contexts[1].vm.id, contexts[1].bo.handle,
				   0xa00000, 4096, 4096, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP))
			goto out;
		stream[0] = (1ULL << 56) | (8ULL << 48) | 0xa00000;
		__sync_synchronize();
		if (isolation_submit(fd, &contexts[0], true) ||
		    ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_GET_STATE, &state) ||
		    !(state.state & DRM_PANTHOR_GROUP_STATE_FATAL_FAULT) ||
		    contexts[1].mapping[1024] != expected[1] ||
		    isolation_submit(fd, &contexts[1], false))
			goto out;
		printf("GPUVM_ISOLATION foreign_va_fault=PASS target=0xa00000 fence=error attacker=fatal victim=preserved victim_resubmit=success\n");
	}
	group_destroy.group_handle = contexts[0].group.group_handle;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &group_destroy))
		goto out;
	contexts[0].group.group_handle = 0;
	if (isolation_rejected("group_rebind_after_destroy",
		ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &duplicate), EACCES))
		goto out;
	old_vm = contexts[0].vm.id;
	destroy.id = old_vm;
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy))
		goto out;
	contexts[0].vm = (struct drm_panthor_vm_create){
		.flags = DRM_PANTHOR_VM_CREATE_ISOLATED,
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &contexts[0].vm))
		goto out;
	if (isolation_rejected("old_bo_new_root",
		isolation_bind(fd, contexts[0].vm.id, contexts[0].bo.handle,
			0x400000, 0, 8192, DRM_PANTHOR_VM_BIND_OP_TYPE_MAP), EACCES))
		goto out;
	printf("GPUVM_ISOLATION root_handle_reused=%u\n", old_vm == contexts[0].vm.id);
	ret = 0;
out:
	if (ret)
		fprintf(stderr, "GPUVM_ISOLATION failure errno=%d (%s)\n", errno, strerror(errno));
	if (other_fd >= 0)
		close(other_fd);
	for (index = 0; index < ARRAY_SIZE(contexts); index++) {
		struct isolation_context *context = &contexts[index];
		struct drm_syncobj_destroy sync_destroy = { .handle = context->sync.handle };
		struct drm_gem_close bo_close = { .handle = context->bo.handle };

		if (context->group.group_handle) {
			group_destroy.group_handle = context->group.group_handle;
			if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_DESTROY, &group_destroy))
				ret = -1;
		}
		if (context->sync.handle && ioctl(fd, DRM_IOCTL_SYNCOBJ_DESTROY, &sync_destroy))
			ret = -1;
		if (context->mapping && munmap((void *)context->mapping, 8192))
			ret = -1;
		if (context->bo.handle && ioctl(fd, DRM_IOCTL_GEM_CLOSE, &bo_close))
			ret = -1;
		if (context->vm.id) {
			destroy.id = context->vm.id;
			if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_DESTROY, &destroy))
				ret = -1;
		}
	}
	return ret;
}
