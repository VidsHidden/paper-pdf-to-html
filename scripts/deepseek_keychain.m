#import <AppKit/AppKit.h>
#import <Security/Security.h>
#import <unistd.h>

static NSDictionary *keychainItem(void) {
    return @{
        (__bridge NSString *)kSecClass: (__bridge NSString *)kSecClassGenericPassword,
        (__bridge NSString *)kSecAttrService: @"codex.paper-pdf-to-html.deepseek",
        (__bridge NSString *)kSecAttrAccount: @"api-key"
    };
}

static int saveKey(void) {
    NSApplication *app = [NSApplication sharedApplication];
    [app setActivationPolicy:NSApplicationActivationPolicyRegular];
    NSMenu *menu = [[NSMenu alloc] init];
    NSMenuItem *edit = [[NSMenuItem alloc] init];
    NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"编辑"];
    [editMenu addItemWithTitle:@"剪切" action:@selector(cut:) keyEquivalent:@"x"];
    [editMenu addItemWithTitle:@"复制" action:@selector(copy:) keyEquivalent:@"c"];
    [editMenu addItemWithTitle:@"粘贴" action:@selector(paste:) keyEquivalent:@"v"];
    [editMenu addItemWithTitle:@"全选" action:@selector(selectAll:) keyEquivalent:@"a"];
    edit.submenu = editMenu;
    [menu addItem:edit];
    app.mainMenu = menu;
    [app activate];

    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"设置 DeepSeek API Key";
    alert.informativeText = @"粘贴你在 DeepSeek 开放平台创建的密钥。点「保存到钥匙串」后，这台 Mac 上的论文转换 Skill 可以复用它。";
    [alert addButtonWithTitle:@"保存到钥匙串"];
    [alert addButtonWithTitle:@"取消"];
    NSSecureTextField *field = [[NSSecureTextField alloc] initWithFrame:NSMakeRect(0, 0, 350, 26)];
    field.placeholderString = @"DeepSeek API Key";
    alert.accessoryView = field;
    alert.window.initialFirstResponder = field;
    [alert.window makeFirstResponder:field];

    if ([alert runModal] != NSAlertFirstButtonReturn) return 2;
    NSString *secret = [field.stringValue stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    field.stringValue = @"";
    NSCharacterSet *invalid = [[NSCharacterSet characterSetWithRange:NSMakeRange(33, 94)] invertedSet];
    if (secret.length == 0 || [secret rangeOfCharacterFromSet:invalid].location != NSNotFound) return 3;

    NSData *data = [secret dataUsingEncoding:NSASCIIStringEncoding];
    NSString *dataKey = (__bridge NSString *)kSecValueData;
    NSDictionary *query = keychainItem();
    NSMutableDictionary *attributes = [query mutableCopy];
    attributes[dataKey] = data;
    attributes[(__bridge NSString *)kSecAttrLabel] = @"Codex 论文翻译 · DeepSeek API Key";
    OSStatus status = SecItemAdd((__bridge CFDictionaryRef)attributes, NULL);
    if (status == errSecDuplicateItem) {
        NSDictionary *changes = @{ dataKey: data };
        status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)changes);
    }
    return status == errSecSuccess ? 0 : 4;
}

static int loadKey(void) {
    // Invoked by the reader with stdout connected to a private pipe.
    if (isatty(STDOUT_FILENO)) return 5;
    NSMutableDictionary *query = [keychainItem() mutableCopy];
    query[(__bridge NSString *)kSecReturnData] = @YES;
    query[(__bridge NSString *)kSecMatchLimit] = (__bridge NSString *)kSecMatchLimitOne;
    CFTypeRef value = NULL;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &value);
    if (status == errSecItemNotFound) return 6;
    if (status != errSecSuccess || value == NULL) return 4;
    NSData *data = CFBridgingRelease(value);
    if (![data isKindOfClass:[NSData class]] || data.length == 0) return 4;
    [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    return 0;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) return 5;
        if (strcmp(argv[1], "save") == 0) return saveKey();
        if (strcmp(argv[1], "get") == 0) return loadKey();
        return 5;
    }
}
