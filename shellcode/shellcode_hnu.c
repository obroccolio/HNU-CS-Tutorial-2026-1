#include <stdio.h>
#include <sys/mman.h>   // 包含 mprotect
#include <unistd.h>     // 包含 sysconf
#include <stdint.h>     // 包含 uintptr_t

// 这是我们的 "数据" (Shellcode + 字符串)
unsigned char shellcode[] = {
    0x48, 0xc7, 0xc0, 0x01, 0x00, 0x00, 0x00, // mov rax, 1 (sys_write)
    0x48, 0xc7, 0xc7, 0x01, 0x00, 0x00, 0x00, // mov rdi, 1 (stdout)
    0x48, 0x8d, 0x35, 0x0a, 0x00, 0x00, 0x00, // lea rsi, [rip+0x0a] (指向下方字符串)
    0x48, 0xc7, 0xc2, 0x19, 0x00, 0x00, 0x00, // mov rdx, 25 (长度)
    0x0f, 0x05,                               // syscall (触发调用)
    0xc3,                                     // ret (返回)
    
    // "I Love Hunan University!\n" 的十六进制 ASCII 码
    0x49, 0x20, 0x4c, 0x6f, 0x76, 0x65, 0x20, 0x48,
    0x75, 0x6e, 0x61, 0x6e, 0x20, 0x55, 0x6e, 0x69,
    0x76, 0x65, 0x72, 0x73, 0x69, 0x74, 0x79, 0x21, 0x0a
};

int main() {
    printf("[*] System Hacker Mode Activated\n");
    printf("[*] Shellcode address: %p\n", (void*)shellcode);

    // 1. 获取系统内存页大小
    size_t page_size = sysconf(_SC_PAGESIZE);

    // 2. 计算页起始地址 (极其关键的页对齐位运算)
    uintptr_t page_start = (uintptr_t)shellcode & ~(page_size - 1);
    printf("[*] Page start address: 0x%lx\n", page_start);

    // 3. 调用 mprotect，修改内存页权限为 可读-可写-可执行 (R-W-X)
    if (mprotect((void *)page_start, page_size, PROT_READ | PROT_WRITE | PROT_EXEC) == -1) {
        perror("[-] mprotect failed");
        return 1;
    }
    printf("[+] NX Bit bypassed successfully using mprotect!\n");
    printf("[+] Executing data array as machine instructions...\n\n");

    // 4. 强转函数指针并执行！
    void (*execute_shellcode)() = (void (*)())shellcode;
    execute_shellcode();

    printf("\n[+] Execution finished safely.\n");
    return 0;
}
