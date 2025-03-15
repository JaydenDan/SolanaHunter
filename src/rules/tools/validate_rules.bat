@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo 🔍 开始校验规则文件...
echo.

:: 初始化变量
set "all_valid=true"
set "all_rule_ids="

:: 遍历当前目录下的所有JSON文件
for %%F in (*.json) do (
    echo 📝 校验文件: %%F
    
    :: 检查文件格式
    findstr /r /c:"^{" "%%F" >nul 2>&1
    if errorlevel 1 (
        echo ❌ JSON格式错误
        set "all_valid=false"
        goto :continue
    )
    
    :: 检查rules字段
    findstr /r /c:"\"rules\"" "%%F" >nul 2>&1
    if errorlevel 1 (
        echo ❌ 缺少'rules'字段
        set "all_valid=false"
        goto :continue
    )
    
    :: 提取并检查规则ID
    for /f "tokens=*" %%I in ('findstr /r /c:"\"id\":" "%%F"') do (
        set "line=%%I"
        set "line=!line:*id\":=!"
        set "line=!line:,=!"
        set "line=!line:"=!"
        set "line=!line: =!"
        
        :: 检查ID是否重复
        echo.!all_rule_ids! | findstr /i /c:"!line!" >nul 2>&1
        if not errorlevel 1 (
            echo ❌ 发现重复的规则ID: !line!
            set "all_valid=false"
        ) else (
            set "all_rule_ids=!all_rule_ids! !line!"
        )
    )
    
    :: 检查必需字段
    for %%K in (name condition action enable) do (
        findstr /r /c:"\"%%K\"" "%%F" >nul 2>&1
        if errorlevel 1 (
            echo ❌ 缺少必需字段: '%%K'
            set "all_valid=false"
        )
    )
    
    if "!all_valid!"=="true" (
        echo ✅ 验证通过
    )
    
    :continue
    echo.
)

if "%all_valid%"=="true" (
    echo ✨ 所有规则文件验证通过！
) else (
    echo ❌ 规则文件验证失败，请修复以上错误。
)

echo.
echo 按回车键退出...
pause > nul