# GPUVM 隔离探针

`panthor_ioctl_smoke --gpuvm-isolation /dev/dri/renderD128`用于Realm Client前端，构建入口与其他模式相同。源码位于`gpuvm_isolation.h`，由smoke主程序包含；不是独立安装的头文件。完整双Client runner在每侧执行此模式，并检查Proxy域注册时的GPU权限/回收自测。

每个受测GPUVM设置`DRM_PANTHOR_VM_CREATE_ISOLATED`，由Proxy强制执行一个生命周期只允许一个Group；普通Mesa GPUVM仍允许域内共享Group，不提供组内隔离承诺。

探针检查同一GPUVM的第二个Group、活动根销毁、跨GPUVM普通/只读别名、越界BO/保留VA、外部session句柄、旧BO借VM编号复用替换根，以及销毁Group后的同根重建拒绝。同根只读别名作为正例保留。

两个Group各使用独立GPUVM，在相同GPU VA `0x401000`交替执行32次真实CSF LOAD/STORE，检查各自独立canary、读取值及真实sync-file fence成功。CSF编码按Mesa `mesa-25.0.7`的`src/panfrost/lib/genxml/v10.xml`和`cs_builder.h`核对，另含WAIT与cache clean/invalidate；不把NOP提交或ioctl成功当作GPU读写证明。

Proxy manager自测另检查GPU权限降权、控制页类型拒绝、foreign owner、旧generation拒绝、free后pin仍阻止backing复用，以及最后unpin后清零再复用。

探针先poll导出的sync-file，再读取真实完成状态；Client/Proxy内部snapshot等待保留原生fence错误，普通DRM等待语义不变。外部session的BO句柄由Client本地表拒绝，管理器自测另独立检查foreign owner，不能将前者写成绕过Client的原始恶意RPC测试。

只有所有检查通过才输出`PANTHOR_IOCTL_SMOKE=GPUVM_ISOLATION_PASS`。该模式不注入GPU故障。

独立模式`--gpuvm-fault-isolation`在上述检查外，让攻击Group执行CSF LOAD，读取仅映射在受害Group中的`0xa00000`，要求攻击者fence报告错误、Group进入fatal状态、受害canary不变且受害Group再次实际执行成功。完整入口使用`run-realm-xshm.py --workload compute --gpu-fault-isolation`；runner独立记录新增的准确故障行和目标VA，只将这条预期翻译故障从最终健康失败列表中单列，其余故障仍失败。该模式成功标记为`PANTHOR_IOCTL_SMOKE=GPUVM_FAULT_ISOLATION_PASS`，不能仅凭超时认为访问被保护。

两种模式均不覆盖片上残留或侧信道。真实页表/配置/控制内存的物理保护按目标平台已有能力处理；不能把此探针称为完整Mali指令验证器。
