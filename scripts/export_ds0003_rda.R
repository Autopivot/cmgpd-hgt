#!/usr/bin/env Rscript
# Export the DS0003 (life events + estimated income) .rda data frame to a
# gzip CSV containing only the columns we need for the V5 narrative agents.
# Usage: Rscript export_ds0003_rda.R <input.rda> <output.csv.gz>
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript export_ds0003_rda.R <input.rda> <output.csv.gz>")
}
input_path <- args[1]
output_path <- args[2]

env <- new.env()
load(input_path, envir = env)
# Per repo notes the DS0003 data frame is named `da27063.0003`. Fall back to
# the first object in the environment if the name has changed in a future
# ICPSR release.
obj_name <- if ("da27063.0003" %in% ls(env)) "da27063.0003" else ls(env)[1]
df <- get(obj_name, envir = env)

keep_cols <- c("PERSON_ID", "YEAR", "EVENT_1", "EVENT_2", "ESTIMATED_INCOME")
missing <- setdiff(keep_cols, names(df))
if (length(missing) > 0) {
  stop(sprintf("DS0003 frame '%s' is missing expected columns: %s",
               obj_name, paste(missing, collapse = ", ")))
}
df <- df[, keep_cols]

con <- gzfile(output_path, "w")
write.csv(df, con, row.names = FALSE)
close(con)
cat(sprintf("Wrote %d rows × %d cols from object '%s'\n",
            nrow(df), ncol(df), obj_name))
