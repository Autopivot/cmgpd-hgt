#!/usr/bin/env Rscript
# Export DS0003 (life events + estimated income) to a gzip CSV containing only
# the columns the V5 narrative agents need.
#
# Schema notes (verified from 27063-0003-Data.rda, 1,513,357 rows x 51 cols):
#   * DS0003 has NO PERSON_ID or YEAR columns. The join key is RECORD_NUMBER
#     (zero-padded factor like "000000001"), which matches DS0001 1:1.
#   * EVENT_1 / EVENT_2 are R factors with labelled levels like "(1) Death".
#     We strip the integer code out of each level so the Python loader can
#     translate it via event_value_labels.json. Empty / NA cells become -99.
#   * ESTIMATED_INCOME is numeric (NA preserved as empty).
#
# Usage: Rscript export_ds0003_rda.R <input.rda> <output.csv.gz>

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript export_ds0003_rda.R <input.rda> <output.csv.gz>")
}
input_path <- args[1]
output_path <- args[2]

env <- new.env()
load(input_path, envir = env)
obj_name <- if ("da27063.0003" %in% ls(env)) "da27063.0003" else ls(env)[1]
df <- get(obj_name, envir = env)

required <- c("RECORD_NUMBER", "EVENT_1", "EVENT_2", "ESTIMATED_INCOME")
missing <- setdiff(required, names(df))
if (length(missing) > 0) {
  stop(sprintf("DS0003 frame '%s' missing expected columns: %s",
               obj_name, paste(missing, collapse = ", ")))
}

# Pull the leading "(N)" out of factor labels like "(1) Death". NA -> -99 so
# the Python side has a uniform integer column to filter against missing_code.
extract_code <- function(x) {
  s <- as.character(x)
  code <- suppressWarnings(as.integer(sub("^\\(([0-9-]+)\\).*$", "\\1", s)))
  code[is.na(code)] <- -99L
  code
}

out <- data.frame(
  RECORD_NUMBER    = as.integer(as.character(df$RECORD_NUMBER)),  # strips zero-padding
  EVENT_1          = extract_code(df$EVENT_1),
  EVENT_2          = extract_code(df$EVENT_2),
  ESTIMATED_INCOME = as.numeric(df$ESTIMATED_INCOME),
  stringsAsFactors = FALSE
)

if (any(is.na(out$RECORD_NUMBER))) {
  stop("RECORD_NUMBER contained values that did not parse to integer")
}

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
con <- gzfile(output_path, "w")
write.csv(out, con, row.names = FALSE, na = "")
close(con)

cat(sprintf("Wrote %d rows x %d cols from object '%s' to %s\n",
            nrow(out), ncol(out), obj_name, output_path))
