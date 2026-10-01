args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop("usage: Rscript extract_nfl_ingame_checkpoint.R SOURCE_ROOT OUTPUT_CSV")
}

root <- normalizePath(args[[1]], mustWork = TRUE)
output <- args[[2]]
games <- read.csv(file.path(root, "cohort.csv"), stringsAsFactors = FALSE)
if (nrow(games) != 195L || anyDuplicated(games$game_id)) {
  stop("exact 195-game Train cohort required")
}

clock_seconds <- function(value) {
  pieces <- strsplit(as.character(value), ":", fixed = TRUE)[[1]]
  if (length(pieces) != 2L) return(NA_integer_)
  minute <- suppressWarnings(as.integer(pieces[[1]]))
  second <- suppressWarnings(as.integer(pieces[[2]]))
  if (is.na(minute) || is.na(second) || minute < 0L || minute > 15L ||
      second < 0L || second > 59L) return(NA_integer_)
  minute * 60L + second
}

parse_utc <- function(value) {
  as.POSIXct(as.character(value), format = "%Y-%m-%dT%H:%M:%OSZ", tz = "UTC")
}

yardline_to_goal <- function(value, possession) {
  text <- trimws(as.character(value))
  if (text == "50") return(50)
  pieces <- strsplit(text, " +")[[1]]
  if (length(pieces) != 2L) return(NA_real_)
  yard <- suppressWarnings(as.numeric(pieces[[2]]))
  if (is.na(yard) || yard < 0 || yard > 50) return(NA_real_)
  if (pieces[[1]] == possession) 100 - yard else yard
}

score_before <- function(detail, decision_order) {
  summaries <- detail$scoringSummaries
  plays <- detail$plays
  if (!is.data.frame(summaries) || nrow(summaries) == 0L) return(c(0, 0))
  required <- c("playId", "patPlayId", "homeScore", "visitorScore")
  if (!all(required %in% names(summaries))) return(c(NA_real_, NA_real_))
  score_positions <- match(as.character(summaries$playId), as.character(plays$playId))
  pat_positions <- match(as.character(summaries$patPlayId), as.character(plays$playId))
  score_order <- rep(NA_real_, length(score_positions))
  pat_order <- rep(NA_real_, length(pat_positions))
  score_valid <- !is.na(score_positions) & !is.na(plays$orderSequence[score_positions])
  pat_valid <- !is.na(pat_positions) & !is.na(plays$orderSequence[pat_positions]) &
    !is.na(summaries$patPlayId) & summaries$patPlayId > 0
  score_order[score_valid] <- plays$orderSequence[score_positions[score_valid]]
  pat_order[pat_valid] <- plays$orderSequence[pat_positions[pat_valid]]
  completed_order <- score_order
  completed_order[pat_valid] <- pmax(
    score_order[pat_valid], pat_order[pat_valid], na.rm = TRUE
  )
  prior <- which(!is.na(completed_order) & completed_order < decision_order)
  if (!length(prior)) return(c(0, 0))
  selected <- prior[[which.max(completed_order[prior])]]
  c(summaries$homeScore[[selected]], summaries$visitorScore[[selected]])
}

rows <- vector("list", nrow(games))
for (i in seq_len(nrow(games))) {
  game_id <- games$game_id[[i]]
  detail <- readRDS(file.path(root, "pbp", paste0(game_id, ".rds")))$data$viewer$gameDetail
  plays <- detail$plays
  required <- c(
    "playId", "orderSequence", "playType", "quarter", "clockTime", "down", "goalToGo", "playDeleted",
    "timeOfDay", "yardLine", "yardsToGo", "possessionTeam.abbreviation"
  )
  if (!is.data.frame(plays) || !all(required %in% names(plays))) {
    rows[[i]] <- data.frame(
      game_id = game_id, status = "invalid_pbp_schema", detail = "required pre-play field missing"
    )
    next
  }
  numeric_order <- suppressWarnings(as.numeric(plays$orderSequence))
  play_ids <- as.character(plays$playId)
  summaries <- detail$scoringSummaries
  scoring_ids <- character()
  if (is.data.frame(summaries) && nrow(summaries)) {
    scoring_ids <- as.character(c(
      summaries$playId,
      summaries$patPlayId[!is.na(summaries$patPlayId) & summaries$patPlayId > 0]
    ))
  }
  causal_identity <- (
    !is.na(plays$playDeleted) & !plays$playDeleted &
      !is.na(plays$timeOfDay) & nzchar(plays$timeOfDay) &
      !is.na(plays$playType) & plays$playType != "UNSPECIFIED"
  ) | play_ids %in% scoring_ids
  if (any(is.na(numeric_order)) || any(!is.finite(numeric_order)) ||
      anyDuplicated(numeric_order[causal_identity]) || any(is.na(play_ids)) ||
      any(!nzchar(play_ids)) || anyDuplicated(play_ids)) {
    rows[[i]] <- data.frame(
      game_id = game_id, status = "invalid_pbp_identity", detail = "playId/orderSequence is missing, duplicate, or nonfinite"
    )
    next
  }
  clock <- vapply(plays$clockTime, clock_seconds, integer(1))
  eligible <- !is.na(plays$quarter) & plays$quarter == 3L &
    !is.na(plays$playDeleted) & !plays$playDeleted &
    !is.na(plays$timeOfDay) & nzchar(plays$timeOfDay) &
    !is.na(clock) & clock <= 8L * 60L &
    !is.na(plays$down) & plays$down >= 1L & plays$down <= 4L &
    !is.na(plays$yardsToGo) &
    !is.na(plays$yardLine) & nzchar(plays$yardLine) &
    !is.na(plays$possessionTeam.abbreviation) &
    nzchar(plays$possessionTeam.abbreviation)
  positions <- which(eligible)
  if (!length(positions)) {
    rows[[i]] <- data.frame(
      game_id = game_id, status = "no_fixed_checkpoint", detail = "no eligible Q3 clock<=08:00 pre-play row"
    )
    next
  }
  positions <- positions[order(numeric_order[positions])]
  selected <- positions[[1]]
  decision_time <- parse_utc(plays$timeOfDay[[selected]])
  possession <- as.character(plays$possessionTeam.abbreviation[[selected]])
  home <- as.character(detail$homeTeam$abbreviation)
  away <- as.character(detail$visitorTeam$abbreviation)
  yards_to_goal <- yardline_to_goal(plays$yardLine[[selected]], possession)
  score <- score_before(detail, numeric_order[[selected]])
  if (is.na(decision_time) || is.na(yards_to_goal) || any(is.na(score)) ||
      !(possession %in% c(home, away))) {
    rows[[i]] <- data.frame(
      game_id = game_id, status = "invalid_checkpoint_state", detail = "checkpoint time, score, team, or field position invalid"
    )
    next
  }
  possession_is_home <- as.integer(possession == home)
  possession_sign <- if (possession_is_home == 1L) 1 else -1
  seconds_remaining <- (4L - 3L) * 900L + clock[[selected]]
  home_score_diff <- score[[1]] - score[[2]]
  rows[[i]] <- data.frame(
    game_id = game_id,
    status = "eligible",
    detail = "",
    play_id = as.character(plays$playId[[selected]]),
    order_sequence = numeric_order[[selected]],
    decision_time_utc = format(decision_time, "%Y-%m-%dT%H:%M:%OS3Z", tz = "UTC"),
    quarter = 3L,
    quarter_clock_seconds = clock[[selected]],
    regulation_seconds_remaining = seconds_remaining,
    home_score_diff_pre = home_score_diff,
    possession_is_home = possession_is_home,
    down = as.integer(plays$down[[selected]]),
    yards_to_go = as.numeric(plays$yardsToGo[[selected]]),
    goal_to_go = as.integer(isTRUE(plays$goalToGo[[selected]])),
    yards_to_opponent_goal = yards_to_goal,
    home_possession_field_advantage = possession_sign * ((50 - yards_to_goal) / 50),
    score_time_ratio_k4 = home_score_diff * exp(4 * (1 - seconds_remaining / 3600)),
    home_team = home,
    away_team = away,
    stringsAsFactors = FALSE
  )
}

all_names <- unique(unlist(lapply(rows, names)))
rows <- lapply(rows, function(row) {
  missing <- setdiff(all_names, names(row))
  for (name in missing) row[[name]] <- NA
  row[all_names]
})
result <- do.call(rbind, rows)
if (nrow(result) != 195L || anyDuplicated(result$game_id)) {
  stop("checkpoint extraction did not preserve the full denominator")
}
write.csv(result, output, row.names = FALSE, na = "")
