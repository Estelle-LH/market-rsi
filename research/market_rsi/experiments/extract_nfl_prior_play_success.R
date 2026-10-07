args <- commandArgs(trailingOnly = TRUE)

parse_utc <- function(value) {
  suppressWarnings(as.POSIXct(
    as.character(value), format = "%Y-%m-%dT%H:%M:%OSZ", tz = "UTC"
  ))
}

summarize_prior_success <- function(plays, home, away, anchor_play_id, anchor_order) {
  if (length(home) != 1L || length(away) != 1L || is.na(home) || is.na(away) ||
      !nzchar(home) || !nzchar(away) || home == away) {
    return(list(status = "invalid_team_identity", detail = "home/away identity is invalid"))
  }
  required <- c(
    "playId", "orderSequence", "playType", "down", "playDeleted",
    "timeOfDay", "yards", "yardsToGo", "possessionTeam.abbreviation"
  )
  if (!is.data.frame(plays) || !all(required %in% names(plays))) {
    return(list(status = "invalid_pbp_schema", detail = "required prior-play field missing"))
  }
  order_value <- suppressWarnings(as.numeric(plays$orderSequence))
  play_id <- as.character(plays$playId)
  if (any(is.na(order_value)) || any(!is.finite(order_value)) ||
      any(is.na(play_id)) || any(!nzchar(play_id)) || anyDuplicated(play_id)) {
    return(list(status = "invalid_pbp_identity", detail = "playId/orderSequence is missing, duplicate, or nonfinite"))
  }
  anchor_position <- which(play_id == as.character(anchor_play_id))
  if (length(anchor_position) != 1L ||
      order_value[[anchor_position]] != as.numeric(anchor_order)) {
    return(list(status = "anchor_mismatch", detail = "frozen v0 anchor identity/order changed"))
  }

  # Causal boundary: subset by identity/order first.  Eligibility fields are
  # then read only from strictly-prior rows, never from the anchor or later.
  prior_positions <- which(order_value < as.numeric(anchor_order))
  prior_plays <- plays[prior_positions, , drop = FALSE]
  prior_order <- order_value[prior_positions]
  play_type <- as.character(prior_plays$playType)
  possession <- as.character(prior_plays$possessionTeam.abbreviation)
  down <- suppressWarnings(as.numeric(prior_plays$down))
  yards <- suppressWarnings(as.numeric(prior_plays$yards))
  yards_to_go <- suppressWarnings(as.numeric(prior_plays$yardsToGo))
  timed <- !is.na(parse_utc(prior_plays$timeOfDay))
  typed <- !is.na(play_type) & nzchar(play_type) & play_type != "UNSPECIFIED"
  nondeleted <- !is.na(prior_plays$playDeleted) &
    !as.logical(prior_plays$playDeleted)
  causal_identity <- nondeleted & timed & typed
  if (anyDuplicated(prior_order[causal_identity])) {
    return(list(status = "invalid_pbp_identity", detail = "causal orderSequence is duplicated"))
  }
  exact_possession <- !is.na(possession) & possession %in% c(home, away)
  eligible <- nondeleted & timed & typed &
    !is.na(down) & down %in% 1:4 &
    !is.na(yards) & is.finite(yards) &
    !is.na(yards_to_go) & is.finite(yards_to_go) & exact_possession

  threshold <- rep(NA_real_, length(down))
  first_down <- which(!is.na(down) & down == 1)
  second_down <- which(!is.na(down) & down == 2)
  late_down <- which(!is.na(down) & down %in% c(3, 4))
  threshold[first_down] <- 0.45 * yards_to_go[first_down]
  threshold[second_down] <- 0.60 * yards_to_go[second_down]
  threshold[late_down] <- yards_to_go[late_down]
  success <- eligible & yards >= threshold
  home_eligible <- eligible & possession == home
  away_eligible <- eligible & possession == away
  home_count <- sum(home_eligible)
  away_count <- sum(away_eligible)
  if (home_count == 0L || away_count == 0L) {
    return(list(
      status = "missing_side_eligible_plays",
      detail = "home or away has zero strictly-prior eligible plays",
      home_eligible_plays = home_count,
      away_eligible_plays = away_count
    ))
  }
  home_successes <- sum(success & home_eligible)
  away_successes <- sum(success & away_eligible)
  home_rate <- home_successes / home_count
  away_rate <- away_successes / away_count
  list(
    status = "eligible",
    detail = "",
    home_eligible_plays = home_count,
    home_successes = home_successes,
    away_eligible_plays = away_count,
    away_successes = away_successes,
    home_success_rate = home_rate,
    away_success_rate = away_rate,
    home_minus_away_success_rate = home_rate - away_rate
  )
}

if (length(args) == 1L && args[[1]] == "--self-test") {
  plays <- data.frame(
    playId = as.character(1:12),
    orderSequence = 1:12,
    playType = rep("RUSH", 12),
    down = c(1, 2, 3, 4, 1, 2, 3, 4, 1, 1, 1, 1),
    playDeleted = c(FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, FALSE),
    timeOfDay = c(rep("2025-01-01T00:00:00.000Z", 9), "", "2025-01-01T00:00:00.000Z", "2025-01-01T00:00:00.000Z"),
    yards = c(5, 5, 10, 9, 4, 6, 9, 10, 99, 99, 99, 99),
    yardsToGo = rep(10, 12),
    possessionTeam.abbreviation = c(rep("H", 4), rep("A", 4), "H", "A", "H", "A"),
    stringsAsFactors = FALSE
  )
  # Rows 11 and 12 are the anchor and a later play and must never contribute,
  # even though their yards would make them successful.
  result <- summarize_prior_success(plays, "H", "A", "11", 11)
  stopifnot(result$status == "eligible")
  stopifnot(result$home_eligible_plays == 4L, result$away_eligible_plays == 4L)
  stopifnot(result$home_successes == 2L, result$away_successes == 2L)
  stopifnot(result$home_minus_away_success_rate == 0)
  plays$possessionTeam.abbreviation[5:8] <- "H"
  missing <- summarize_prior_success(plays, "H", "A", "11", 11)
  stopifnot(missing$status == "missing_side_eligible_plays")
  writeLines("prior-play-success self-test PASS")
  quit(save = "no", status = 0L)
}

if (length(args) != 3L) {
  stop("usage: Rscript extract_nfl_prior_play_success.R SOURCE_ROOT V0_ANCHORS_CSV OUTPUT_CSV")
}

root <- normalizePath(args[[1]], mustWork = TRUE)
anchor_path <- normalizePath(args[[2]], mustWork = TRUE)
output <- args[[3]]
games <- read.csv(file.path(root, "cohort.csv"), stringsAsFactors = FALSE)
anchors <- read.csv(anchor_path, stringsAsFactors = FALSE)
if (nrow(games) != 195L || anyDuplicated(games$game_id) ||
    nrow(anchors) != 195L || anyDuplicated(anchors$game_id) ||
    !setequal(as.character(games$game_id), as.character(anchors$game_id))) {
  stop("exact matching 195-game Train cohort and v0 anchors required")
}
anchor_by_game <- match(as.character(games$game_id), as.character(anchors$game_id))
if (any(is.na(anchor_by_game)) || any(anchors$status[anchor_by_game] != "eligible")) {
  stop("all frozen v0 anchors must be eligible")
}

rows <- vector("list", nrow(games))
for (i in seq_len(nrow(games))) {
  game_id <- as.character(games$game_id[[i]])
  anchor <- anchors[anchor_by_game[[i]], ]
  detail <- readRDS(file.path(root, "pbp", paste0(game_id, ".rds")))$data$viewer$gameDetail
  home <- as.character(detail$homeTeam$abbreviation)
  away <- as.character(detail$visitorTeam$abbreviation)
  result <- summarize_prior_success(
    detail$plays, home, away, as.character(anchor$play_id),
    as.numeric(anchor$order_sequence)
  )
  rows[[i]] <- data.frame(
    game_id = game_id,
    status = result$status,
    detail = result$detail,
    anchor_play_id = as.character(anchor$play_id),
    anchor_order_sequence = as.numeric(anchor$order_sequence),
    home_team = home,
    away_team = away,
    home_eligible_plays = if (!is.null(result$home_eligible_plays)) result$home_eligible_plays else NA,
    home_successes = if (!is.null(result$home_successes)) result$home_successes else NA,
    away_eligible_plays = if (!is.null(result$away_eligible_plays)) result$away_eligible_plays else NA,
    away_successes = if (!is.null(result$away_successes)) result$away_successes else NA,
    home_success_rate = if (!is.null(result$home_success_rate)) result$home_success_rate else NA,
    away_success_rate = if (!is.null(result$away_success_rate)) result$away_success_rate else NA,
    home_minus_away_success_rate = if (!is.null(result$home_minus_away_success_rate)) result$home_minus_away_success_rate else NA,
    stringsAsFactors = FALSE
  )
}
result <- do.call(rbind, rows)
if (nrow(result) != 195L || anyDuplicated(result$game_id)) {
  stop("prior-play extraction did not preserve the full 195-game denominator")
}
write.csv(result, output, row.names = FALSE, na = "")
