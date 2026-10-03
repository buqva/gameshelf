// SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Filtering, sorting and grouping for the game grid.
 *
 * Pure functions over the arrays the backend produced, kept out of the QML so
 * the view files stay about layout. No i18n in here: it is a `.pragma library`,
 * which has no QML context, so anything user-visible comes back as an id for
 * the caller to translate.
 */
.pragma library

/* Split a query into terms. Every term must appear somewhere in the game's
 * text, which makes "cyber 2077" find "Cyberpunk 2077" without needing the
 * words in order. */
function terms(query) {
    return String(query || "")
        .toLowerCase()
        .split(/\s+/)
        .filter(function (term) { return term.length > 0; });
}

function matches(game, queryTerms) {
    if (queryTerms.length === 0) {
        return true;
    }
    // sort_title has the trademark symbols stripped, so searching "borderlands 4"
    // finds "Borderlands® 4" whichever of the two the term happens to hit.
    var haystack = (String(game.title || "") + " " + String(game.sort_title || "")).toLowerCase();
    for (var i = 0; i < queryTerms.length; ++i) {
        if (haystack.indexOf(queryTerms[i]) === -1) {
            return false;
        }
    }
    return true;
}

/* A "source" is a launcher, or one store within a launcher: Steam, Epic, GOG.
 * It is what the filter chips select on. The id deliberately mirrors the first
 * two fields of the game key. */
function sourceId(game) {
    return String(game.provider) + ":" + (game.store ? String(game.store) : "-");
}

/* Every source that has at least one game, in the order the games arrive, with
 * the launcher's display name and icon taken from its report. A provider the
 * QML has never heard of still gets a usable chip. */
function sources(games, reports) {
    var byId = {};
    for (var r = 0; r < (reports || []).length; ++r) {
        byId[reports[r].id] = reports[r];
    }

    var seen = {};
    var found = [];
    for (var i = 0; i < games.length; ++i) {
        var game = games[i];
        var id = sourceId(game);
        if (seen[id]) {
            seen[id].count += 1;
            continue;
        }
        var report = byId[game.provider] || {};
        var entry = {
            id: id,
            provider: String(game.provider),
            store: game.store ? String(game.store) : "",
            name: String(report.name || game.provider),
            icon: String(report.icon || "applications-games"),
            count: 1
        };
        seen[id] = entry;
        found.push(entry);
    }
    return found;
}

function iconForProvider(providerId, reports) {
    for (var i = 0; i < (reports || []).length; ++i) {
        if (reports[i].id === providerId) {
            return String(reports[i].icon || "applications-games");
        }
    }
    return "applications-games";
}

function nameForProvider(providerId, reports) {
    for (var i = 0; i < (reports || []).length; ++i) {
        if (reports[i].id === providerId) {
            return String(reports[i].name || providerId);
        }
    }
    return String(providerId);
}

/* Missing values sort last in both "recent" and "playtime": a game that has
 * never been played should not lead a most-recent list. */
function compareDescendingNullsLast(left, right) {
    var a = (left === null || left === undefined) ? -1 : left;
    var b = (right === null || right === undefined) ? -1 : right;
    return b - a;
}

function compareNames(left, right) {
    var a = String(left.sort_title || left.title || "");
    var b = String(right.sort_title || right.title || "");
    if (a < b) return -1;
    if (a > b) return 1;
    // The key breaks ties, so two games of the same name keep a stable order
    // between runs instead of swapping places.
    return String(left.key) < String(right.key) ? -1 : 1;
}

function comparator(sortMode, favorites, favoritesFirst) {
    var starred = {};
    if (favoritesFirst) {
        for (var i = 0; i < (favorites || []).length; ++i) {
            starred[favorites[i]] = true;
        }
    }

    return function (left, right) {
        if (favoritesFirst) {
            var leftStar = starred[left.key] === true;
            var rightStar = starred[right.key] === true;
            if (leftStar !== rightStar) {
                return leftStar ? -1 : 1;
            }
        }
        var order = 0;
        if (sortMode === "recent") {
            order = compareDescendingNullsLast(left.last_played, right.last_played);
        } else if (sortMode === "playtime") {
            order = compareDescendingNullsLast(left.playtime_minutes, right.playtime_minutes);
        }
        return order !== 0 ? order : compareNames(left, right);
    };
}

/* Whether an entry is a launcher application rather than a game. The backend
 * marks them; nothing here needs to know which launchers exist. */
function isLauncher(entry) {
    return !!(entry && entry.extra && entry.extra.is_launcher);
}

/* The launcher tiles to pin ahead of the games.
 *
 * They follow the search box and the chips, so a filtered grid stays coherent,
 * but never the sort or the favourites: their whole job is to be first. A chip
 * selects a source like "heroic:epic", and the launcher that owns that store is
 * the one that stays — picking "Epic" keeps the Heroic tile, which is what you
 * would open to do something about an Epic game.
 */
function visibleLaunchers(launchers, query, source) {
    var queryTerms = terms(query);
    var wantedProvider = source && source.length > 0 ? String(source).split(":")[0] : null;
    var result = [];
    for (var i = 0; i < (launchers || []).length; ++i) {
        var launcher = launchers[i];
        if (wantedProvider !== null && String(launcher.provider) !== wantedProvider) {
            continue;
        }
        if (matches(launcher, queryTerms)) {
            result.push(launcher);
        }
    }
    return result;
}

/* The one entry point the view uses: everything the grid should show, in order. */
function visible(games, query, source, sortMode, favorites, favoritesFirst) {
    var queryTerms = terms(query);
    var wanted = source && source.length > 0 ? source : null;
    var result = [];
    for (var i = 0; i < games.length; ++i) {
        var game = games[i];
        if (wanted !== null && sourceId(game) !== wanted) {
            continue;
        }
        if (matches(game, queryTerms)) {
            result.push(game);
        }
    }
    result.sort(comparator(sortMode, favorites, favoritesFirst));
    return result;
}
