// OpenClaw Office UI - Internationalization (i18n)
// Supports: Chinese (zh), English (en), Japanese (ja)
// Loaded as external script to reduce inline JS in index.html

let uiLang = 'en';

const I18N = {
    zh: {
        controlTitle: 'Star 状态',
        btnIdle: '待命', btnWork: '工作', btnSync: '同步', btnError: '报警', btnDecor: '装修房间',
        drawerTitle: '装修房间 · 资产侧边栏', drawerClose: '关闭',
        authTitle: '请输入装修验证码', authPlaceholder: '输入验证码', authVerify: '验证', authDefaultPassHint: '默认密码：1234（可随时让我帮你改，建议改成强密码）',
        drawerVisibilityTip: '可见性：点击条目右侧眼睛按钮切换该资产显示',
        hideDrawer: '👁 隐藏侧边栏', showDrawer: '👁 显示侧边栏',
        assetHide: '隐藏', assetShow: '显示',
        resetToDefault: '重置为默认资产', restorePrevAsset: '用上一版',
        btnMove: '📦 搬新家', btnHome: '🐚 回老家', btnHomeLast: '↩️ 回上一个家', btnHomeFavorite: '⭐ 收藏这个家', btnBroker: '🤝 找中介', btnDIY: '🪚 自己装', btnBrokerGo: '听中介的',
        homeFavTitle: '🏠 收藏的家', homeFavEmpty: '还没有收藏，先点"⭐ 收藏这个家"', homeFavApply: '替换到当前地图', homeFavDelete: '删除', homeFavSaved: '✅ 已收藏当前地图', homeFavApplied: '✅ 已替换为收藏地图', homeFavDeleted: '🗑️ 已删除收藏',
        brokerHint: '你会给龙虾推荐什么样的房子',
        brokerPromptPh: '例如：故宫主题、莫奈风格、地牢主题、兵马俑主题……',
        brokerNeedPrompt: '请先输入中介方案描述',
        brokerGenerating: '🏘️ 正在按中介方案生成底图，请稍候（约20-90秒）...',
        brokerDone: '✅ 已按中介方案生成并替换底图，正在刷新房间...',
        moveSuccess: '✅ 搬家成功！',
        brokerMissingKey: '❌ 生图失败：缺少 GEMINI API Key，请在下方填写并保存后重试',
        geminiPanelTitle: '🔐 API 设置（可折叠）', geminiHint: '可选：填写你的生图 API Key（留空不影响基础功能）', geminiApiDoc: '📘 如何申请 Google API Key', geminiInputPh: '粘贴 GEMINI_API_KEY（不会回显）', geminiSaveKey: '保存 Key', geminiMaskNoKey: '当前状态：未配置 Key', geminiMaskHasKey: '当前已配置：',
        speedModeLabel: '生成模式', speedFast: '🍌2', speedQuality: '🍌Pro',
        searchPlaceholder: '搜索资产名（如 desk / sofa / star）', loaded: '已加载', allAssets: '全部资产',
        chooseImage: '上传素材', confirmUpload: '确认刷新', uploadPending: '待上传', uploadTarget: '目标',
        assetHintNotInScene: '当前场景未检测到此对象，仍可替换文件（刷新后生效）',
        assetHintDefault: '通用素材：建议保持原图尺寸、透明通道与视觉重心一致，避免错位或失真',
        showCoords: '显示坐标', hideCoords: '隐藏坐标', moveView: 'Move View', lockView: '锁定视野',
        memoTitle: '昨 日 小 记', guestTitle: '访 客 列 表', officeTitle: '海辛小龙虾的办公室',
        loadingOffice: '正在加载 Star 的像素办公室...'
    },
    en: {
        controlTitle: 'Star Status',
        btnIdle: 'Idle', btnWork: 'Work', btnSync: 'Sync', btnError: 'Alert', btnDecor: 'Decorate Room',
        drawerTitle: 'Decorate Room · Asset Sidebar', drawerClose: 'Close',
        authTitle: 'Enter Decor Passcode', authPlaceholder: 'Enter passcode', authVerify: 'Verify', authDefaultPassHint: 'Default passcode: 1234 (ask me anytime to change it; stronger passcode recommended)',
        drawerVisibilityTip: 'Visibility: use the eye button on each row to hide/show that asset',
        hideDrawer: '👁 Hide Drawer', showDrawer: '👁 Show Drawer',
        assetHide: 'Hide', assetShow: 'Show',
        resetToDefault: 'Reset to Default', restorePrevAsset: 'Use Previous',
        btnMove: '📦 New Home', btnHome: '🐚 Go Home', btnHomeLast: '↩️ Last One', btnHomeFavorite: '⭐ Save This Home', btnBroker: '🤝 Broker', btnDIY: '🪚 DIY', btnBrokerGo: 'Follow Broker',
        homeFavTitle: '🏠 Saved Homes', homeFavEmpty: 'No saved homes yet. Tap "⭐ Save This Home" first.', homeFavApply: 'Apply to Current Map', homeFavDelete: 'Delete', homeFavSaved: '✅ Current map saved', homeFavApplied: '✅ Applied saved home', homeFavDeleted: '🗑️ Saved home deleted',
        brokerHint: 'What kind of house would you recommend for Lobster?',
        brokerPromptPh: 'e.g. Forbidden City theme, Monet style, dungeon theme, Terracotta Warriors theme...',
        brokerNeedPrompt: 'Please enter broker style prompt first',
        brokerGenerating: '🏘️ Generating room background from broker plan, please wait (20-90s)...',
        brokerDone: '✅ Broker plan applied and background replaced, refreshing room...',
        moveSuccess: '✅ Move successful!',
        brokerMissingKey: '❌ Generation failed: missing GEMINI API key. Fill it below and retry.',
        geminiPanelTitle: '🔐 API Settings (collapsible)', geminiHint: 'Optional: set your image API key (base features work without it)', geminiApiDoc: '📘 How to get a Google API Key', geminiInputPh: 'Paste GEMINI_API_KEY (input hidden)', geminiSaveKey: 'Save Key', geminiMaskNoKey: 'Current: no key configured', geminiMaskHasKey: 'Configured key:',
        speedModeLabel: 'Render Mode', speedFast: '🍌2', speedQuality: '🍌Pro',
        searchPlaceholder: 'Search assets (desk / sofa / star)', loaded: 'Loaded', allAssets: 'All Assets',
        chooseImage: 'Upload Asset', confirmUpload: 'Apply Refresh', uploadPending: 'Pending Upload', uploadTarget: 'Target',
        assetHintNotInScene: 'This object is not detected in current scene; you can still replace file (effective after refresh)',
        assetHintDefault: 'Generic asset: keep source size, alpha channel, and visual anchor to avoid drift/distortion',
        showCoords: 'Show Coords', hideCoords: 'Hide Coords', moveView: 'Pan View', lockView: 'Lock View',
        memoTitle: 'YESTERDAY NOTES', guestTitle: 'VISITOR LIST', officeTitle: 'Haixin Lobster Office',
        loadingOffice: "Loading Star's pixel office..."
    },
    ja: {
        controlTitle: 'Star ステータス',
        btnIdle: '待機', btnWork: '作業', btnSync: '同期', btnError: '警報', btnDecor: '部屋を編集',
        drawerTitle: '部屋編集・アセットサイドバー', drawerClose: '閉じる',
        authTitle: '編集パスコードを入力', authPlaceholder: 'パスコード入力', authVerify: '認証', authDefaultPassHint: '初期パスコード：1234（いつでも変更を相談可。強固なパス推奨）',
        drawerVisibilityTip: '表示切替：各行右側の目ボタンで資産を表示/非表示',
        hideDrawer: '👁 サイドバーを隠す', showDrawer: '👁 サイドバーを表示',
        assetHide: '非表示', assetShow: '表示',
        resetToDefault: 'デフォルトへ戻す', restorePrevAsset: '前の版へ戻す',
        btnMove: '📦 引っ越し', btnHome: '🐚 実家に戻る', btnHomeLast: '↩️ ひとつ前へ', btnHomeFavorite: '⭐ この家を保存', btnBroker: '🤝 仲介', btnDIY: '🪚 自分で装飾', btnBrokerGo: '仲介に任せる',
        homeFavTitle: '🏠 保存した家', homeFavEmpty: 'まだ保存がありません。先に「⭐ この家を保存」を押してください。', homeFavApply: '現在のマップに適用', homeFavDelete: '削除', homeFavSaved: '✅ 現在のマップを保存しました', homeFavApplied: '✅ 保存した家を適用しました', homeFavDeleted: '🗑️ 保存した家を削除しました',
        brokerHint: 'ロブスターにはどんな家をおすすめしますか',
        brokerPromptPh: '例：故宮テーマ、モネ風、ダンジョン風、兵馬俑テーマ…',
        brokerNeedPrompt: '先に仲介プランの説明を入力してください',
        brokerGenerating: '🏘️ 仲介プランで背景を生成中（20〜90秒）...',
        brokerDone: '✅ 仲介プランを適用して背景を更新しました。部屋を更新中...',
        moveSuccess: '✅ 引っ越し成功！',
        brokerMissingKey: '❌ 生成失敗：GEMINI APIキーが未設定です。下で入力して保存してください。',
        geminiPanelTitle: '🔐 API設定（折りたたみ）', geminiHint: '任意：画像生成APIキーを設定（未設定でも基本機能は利用可）', geminiApiDoc: '📘 Google API Keyの取得方法', geminiInputPh: 'GEMINI_API_KEY を貼り付け（入力は非表示）', geminiSaveKey: 'Keyを保存', geminiMaskNoKey: '現在：キー未設定', geminiMaskHasKey: '設定済みキー：',
        speedModeLabel: '生成モード', speedFast: '🍌2', speedQuality: '🍌Pro',
        searchPlaceholder: 'アセット検索（desk / sofa / star）', loaded: '読み込み済み', allAssets: '全アセット',
        chooseImage: '素材アップロード', confirmUpload: '確定して更新', uploadPending: 'アップロード待ち', uploadTarget: '対象',
        assetHintNotInScene: '現在のシーンでこのオブジェクトは未検出です。ファイル差し替えは可能（更新後に反映）',
        assetHintDefault: '汎用素材：元サイズ・透過・視覚アンカーを維持し、ズレや崩れを防いでください',
        showCoords: '座標表示', hideCoords: '座標非表示', moveView: '視点移動', lockView: '視点固定',
        memoTitle: '昨日のメモ', guestTitle: '訪問者リスト', officeTitle: 'ハイシン・ロブスターのオフィス',
        loadingOffice: 'Star のピクセルオフィスを読み込み中...'
    }
};

function t(key) {
    return (I18N[uiLang] && I18N[uiLang][key]) || key;
}
