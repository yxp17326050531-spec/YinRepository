/* Native Windows GUI launcher. Only Windows system DLLs; no C runtime required. */
#ifndef UNICODE
#define UNICODE
#endif
#include <windows.h>

void mainCRTStartup(void) {
    const DWORD capacity=32768;
    HANDLE heap=GetProcessHeap();
    wchar_t *root=HeapAlloc(heap,HEAP_ZERO_MEMORY,capacity*sizeof(wchar_t));
    wchar_t *python=HeapAlloc(heap,HEAP_ZERO_MEMORY,capacity*sizeof(wchar_t));
    wchar_t *script=HeapAlloc(heap,HEAP_ZERO_MEMORY,capacity*sizeof(wchar_t));
    wchar_t *command=HeapAlloc(heap,HEAP_ZERO_MEMORY,capacity*sizeof(wchar_t));
    STARTUPINFOW *startup=HeapAlloc(heap,HEAP_ZERO_MEMORY,sizeof(STARTUPINFOW));
    PROCESS_INFORMATION *child=HeapAlloc(heap,HEAP_ZERO_MEMORY,sizeof(PROCESS_INFORMATION));
    DWORD result=1;
    if (!root || !python || !script || !command || !startup || !child) goto finish;
    DWORD length=GetModuleFileNameW(NULL,root,capacity);
    if (!length || length>=capacity) goto finish;
    while (length && root[length-1]!=L'\\') length--;
    if (!length) goto finish;
    root[length-1]=0;
    if (length+80>=capacity) goto finish;
    lstrcpyW(python,root);lstrcatW(python,L"\\_internal\\python\\pythonw.exe");
    lstrcpyW(script,root);lstrcatW(script,L"\\_internal\\app\\portable_bootstrap.py");
    if (GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES || GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL,L"Extract the complete ZIP first and keep the _internal folder beside EtheriaAssistant.exe.",L"Etheria Assistant",MB_OK|MB_ICONERROR);
        goto finish;
    }
    wchar_t *arguments=GetCommandLineW();
    if (*arguments==L'\"') {arguments++;while (*arguments && *arguments!=L'\"') arguments++;if (*arguments) arguments++;}
    else {while (*arguments && *arguments!=L' ' && *arguments!=L'\t') arguments++;}
    while (*arguments==L' ' || *arguments==L'\t') arguments++;
    if ((DWORD)(lstrlenW(python)+lstrlenW(script)+lstrlenW(arguments))+8>=capacity) goto finish;
    lstrcpyW(command,L"\"");lstrcatW(command,python);lstrcatW(command,L"\" \"");
    lstrcatW(command,script);lstrcatW(command,L"\" ");lstrcatW(command,arguments);
    SetEnvironmentVariableW(L"ETHERIA_PORTABLE_ROOT",root);
    startup->cb=sizeof(STARTUPINFOW);
    if (!CreateProcessW(python,command,NULL,NULL,FALSE,0,NULL,root,startup,child)) {
        wchar_t error[512];
        FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM|FORMAT_MESSAGE_IGNORE_INSERTS,NULL,GetLastError(),0,error,512,NULL);
        MessageBoxW(NULL,error,L"Etheria Assistant - Runtime startup failed",MB_OK|MB_ICONERROR);
        goto finish;
    }
    CloseHandle(child->hThread);WaitForSingleObject(child->hProcess,INFINITE);
    GetExitCodeProcess(child->hProcess,&result);CloseHandle(child->hProcess);
finish:
    if (root) HeapFree(heap,0,root);
    if (python) HeapFree(heap,0,python);
    if (script) HeapFree(heap,0,script);
    if (command) HeapFree(heap,0,command);
    if (startup) HeapFree(heap,0,startup);
    if (child) HeapFree(heap,0,child);
    ExitProcess(result);
}
