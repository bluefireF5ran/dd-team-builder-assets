// Subscribe to 99 problematic mods that need re-scraping
// These mods were previously scraped with 0 skills/broken names and are no longer on disk
(async function() {
    const need = new Set("2502465345 2525601290 2531791079 2565165380 2572649246 2608626994 2743722561 2812929748 2817045273 2863068028 2863465026 2868111900 2876261390 2879322922 2882385295 2951453412 2985374503 3002789745 3026772660 3034902222 3037175848 3045881665 3059321932 3063258394 3088253088 3106860450 3154632864 3156118387 3163227823 3166564317 3170796124 3170796947 3220013081 3237346773 3252136347 3265771115 3266293876 3268454059 3268455423 3280184294 3283618244 3290790547 3291173004 3309026393 3315284734 3327868060 3336504475 3352861439 3354876341 3355544064 3372687509 3378345708 3382399081 3397134362 3414107333 3415611143 3417575327 3419308929 3424745688 3425790723 3428245706 3429149166 3432168693 3439623342 3444615661 3460839981 3467159384 3473657743 3476482278 3482922464 3491486013 3493216030 3498070483 3527833173 3539954403 3542815014 3550713033 3550738728 3551160477 3560981532 3573206685 3580776814 3581849691 3594656542 3600230865 3600242956 3621826464 3622816274 3631649848 3655423209 3659966915 3659971553 3659971725 3661454250 3666727765 3670010994 3689141481 3701608532 3707874770".split(" "));

    let links = document.querySelectorAll('a[href*="sharedfiles/filedetails/?id="]');
    let found = [];
    links.forEach(link => {
        try {
            let id = new URL(link.href).searchParams.get("id");
            if (id && need.has(id)) found.push(id);
        } catch(e) {}
    });

    if (found.length === 0) return console.log("%cNo missing mods found on this page.", "color: orange; font-size: 14px; font-weight:bold;");

    let unique = [...new Set(found)];
    console.log(`%cFound ${unique.length} missing mods on this page. Subscribing...`, "color: #66c0f4; font-size: 14px; font-weight:bold;");
    let delay = ms => new Promise(r => setTimeout(r, ms));
    let ok = 0, fail = 0;

    for (let id of unique) {
        try {
            let data = await $J.post('https://steamcommunity.com/sharedfiles/subscribe', {
                id: id, appid: "262060", sessionid: window.g_sessionID
            });
            let r = (typeof data === 'object') ? data : JSON.parse(data);
            if (r.success === 1) { ok++; console.log(`%c✅ ${id}`, 'color: #a3da00;'); }
            else { fail++; console.log(`%c⚠️ ${id} code ${r.success}`, 'color: orange;'); }
        } catch(e) { fail++; console.error(`❌ ${id}`); }
        await delay(400);
    }
    console.log(`%cDone! ✅ ${ok} subscribed, ⚠️ ${fail} failed`, "color: #66c0f4; font-size: 14px; font-weight:bold;");
})();
