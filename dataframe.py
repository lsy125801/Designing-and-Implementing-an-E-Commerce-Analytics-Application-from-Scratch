# dataframe.py
# csv parser + dataframe class supporting parsing, filtering, projection,
# groupby/aggregation, join, and some helper analytics for Olist categories.

from typing import Dict, List, Callable, Any, Iterable, Tuple


# helper functions 

def _convert_value(raw: str) -> Any:
    
    #Try to convert a string to int, then float, otherwise keep as string.
    
    s = raw.strip()
    if s == "":
        return None
    # Try int
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    # otherwise keep string
    return s


def _parse_csv_line(line: str, sep: str = ",", quotechar: str = '"') -> List[str]:
    # parse a single csv record 
   
    fields: List[str] = []
    field: List[str] = []
    in_quotes = False
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]

        if ch == quotechar:
            if in_quotes and i + 1 < n and line[i + 1] == quotechar:
                field.append(quotechar)
                i += 2
                continue
            in_quotes = not in_quotes
            i += 1
        elif ch == sep and not in_quotes:
            fields.append("".join(field))
            field = []
            i += 1
        else:
            field.append(ch)
            i += 1

    # last field
    fields.append("".join(field))
    return fields


def _is_complete_record(record: str, quotechar: str = '"') -> bool:
    
    #Check if a CSV record string has balanced quotes.
    
    in_quotes = False
    i = 0
    n = len(record)
    while i < n:
        ch = record[i]
        if ch == quotechar:
            # handle escaped double quotes
            if in_quotes and i + 1 < n and record[i + 1] == quotechar:
                i += 2
                continue
            in_quotes = not in_quotes
        i += 1
    return not in_quotes


#csv parsers

def parse_csv(
    filename,
    sep: str = ",",
    has_header: bool = True,
    chunk_size=None,
) -> "DataFrame | Iterable['DataFrame']":
    
    #Parse a CSV file into a DataFrame.

    
    # chunked mode
    if chunk_size is not None:
        return parse_csv_in_chunks(
            filename,
            sep=sep,
            has_header=has_header,
            chunk_size=chunk_size,
        )

    # full-file mode
    with open(filename, "r", encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line:
            raise ValueError("Empty CSV file")

        if has_header:
            header_line = first_line.rstrip("\n")
            header_parts = _parse_csv_line(header_line, sep=sep)
            # NOTE: this keeps any BOM characters; we handle that later when needed
            columns = [col.strip() for col in header_parts]
        else:
            parts = _parse_csv_line(first_line.rstrip("\n"), sep=sep)
            columns = [f"col{i}" for i in range(len(parts))]

        data: Dict[str, List[Any]] = {c: [] for c in columns}

        # buffer to accumulate logical records
        buffer = ""

        def _try_finish_record(line: str):
            nonlocal buffer
            line = line.rstrip("\n")

            if buffer:
                buffer += "\n" + line
            else:
                buffer = line

            if _is_complete_record(buffer):
                rec = buffer
                buffer = ""
                return rec
            else:
                return None

        # if has_header=False, first_line is data
        if not has_header:
            rec = _try_finish_record(first_line)
            if rec is not None and rec.strip() != "":
                parts = _parse_csv_line(rec, sep=sep)
                if len(parts) != len(columns):
                    raise ValueError(
                        f"Row has {len(parts)} columns, expected {len(columns)}: {rec}"
                    )
                for col, raw_val in zip(columns, parts):
                    data[col].append(_convert_value(raw_val))

        # process rest of file
        for line in f:
            rec = _try_finish_record(line)
            if rec is None:
                continue
            if rec.strip() == "":
                continue

            parts = _parse_csv_line(rec, sep=sep)
            if len(parts) != len(columns):
                raise ValueError(
                    f"Row has {len(parts)} columns, expected {len(columns)}: {rec}"
                )
            for col, raw_val in zip(columns, parts):
                data[col].append(_convert_value(raw_val))

        # leftover buffer
        if buffer.strip() != "":
            raise ValueError(f"Incomplete CSV record at end of file: {buffer}")

    return DataFrame(data)


def parse_csv_in_chunks(
    filename,
    sep: str = ",",
    has_header: bool = True,
    chunk_size: int = 10000,
) -> Iterable["DataFrame"]:

    with open(filename, "r", encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line:
            return  # empty file

        if has_header:
            header_line = first_line.rstrip("\n")
            header_parts = _parse_csv_line(header_line, sep=sep)
            columns = [col.strip() for col in header_parts]
        else:
            parts = _parse_csv_line(first_line.rstrip("\n"), sep=sep)
            columns = [f"col{i}" for i in range(len(parts))]

        data: Dict[str, List[Any]] = {c: [] for c in columns}
        row_count = 0

        # if has_header=False, process first_line as data
        if not has_header:
            parts = _parse_csv_line(first_line.rstrip("\n"), sep==sep)
            if len(parts) != len(columns):
                raise ValueError(
                    f"Row has {len(parts)} columns, expected {len(columns)}: {first_line}"
                )
            for col, raw_val in zip(columns, parts):
                data[col].append(_convert_value(raw_val))
            row_count += 1

        for line in f:
            line = line.rstrip("\n")
            if line.strip() == "":
                continue

            parts = _parse_csv_line(line, sep=sep)
            if len(parts) != len(columns):
                raise ValueError(
                    f"Row has {len(parts)} columns, expected {len(columns)}: {line}"
                )

            for col, raw_val in zip(columns, parts):
                data[col].append(_convert_value(raw_val))
            row_count += 1

            if row_count >= chunk_size:
                yield DataFrame({c: data[c][:] for c in columns})
                data = {c: [] for c in columns}
                row_count = 0

        if row_count > 0:
            yield DataFrame(data)


# dataframe and groupby

class DataFrame:
    def __init__(self, data: Dict[str, List[Any]]):
        # check column lengths
        lengths = {len(v) for v in data.values()} if data else {0}
        if len(lengths) > 1:
            raise ValueError(f"Inconsistent column lengths: {lengths}")
        self._data = data
        self.columns = list(data.keys())
        self._n_rows = lengths.pop() if lengths else 0

    def __len__(self) -> int:
        return self._n_rows

    def __repr__(self) -> str:
        preview_rows = min(5, self._n_rows)
        lines = ["DataFrame("]
        lines.append(f"  columns={self.columns}")
        lines.append(f"  n_rows={self._n_rows}")
        lines.append("  preview=")
        for i in range(preview_rows):
            row = {col: self._data[col][i] for col in self.columns}
            lines.append(f"    {row}")
        if self._n_rows > preview_rows:
            lines.append("    ...")
        lines.append(")")
        return "\n".join(lines)

    # basic access

    def __getitem__(self, key: Any) -> Any:
        """
        - df['col'] -> list of values in that column
        - df[['col1', 'col2']] -> new DataFrame with those columns (projection)
        """
        if isinstance(key, str):
            return self._data[key]
        elif isinstance(key, list):
            return DataFrame({col: self._data[col] for col in key})
        else:
            raise TypeError("__getitem__ key must be str or list of str")

    def row(self, idx: int) -> Dict[str, Any]:
        if idx < 0 or idx >= self._n_rows:
            raise IndexError("row index out of range")
        return {col: self._data[col][idx] for col in self.columns}

    # filtering

    def filter_rows(self, predicate: Callable[[Dict[str, Any]], bool]) -> "DataFrame":
        indices: List[int] = []
        for i in range(self._n_rows):
            row = {col: self._data[col][i] for col in self.columns}
            if predicate(row):
                indices.append(i)

        new_data: Dict[str, List[Any]] = {
            col: [self._data[col][i] for i in indices] for col in self.columns
        }
        return DataFrame(new_data)

    # projection

    def project(self, columns: List[str]) -> "DataFrame":
        return DataFrame({col: self._data[col] for col in columns})

    # group by

    def groupby(self, group_cols: List[str]) -> "GroupBy":
        return GroupBy(self, group_cols)

    # join

    def join(
        self,
        other: "DataFrame",
        left_on: str,
        right_on: str,
        how: str = "inner",
        suffixes: Tuple[str, str] = ("_x", "_y"),
    ) -> "DataFrame":

        # build index on right dataframe
        right_index: Dict[Any, List[int]] = {}
        for j in range(len(other)):
            key = other._data[right_on][j]
            right_index.setdefault(key, []).append(j)

        # prep result columns
        result_data: Dict[str, List[Any]] = {}
        for col in self.columns:
            result_data[col] = []

        # right columns (other)
        right_col_map: Dict[str, str] = {}
        for col in other.columns:
            if col == right_on:
                continue  # don't duplicate the join key
            out_name = col
            if out_name in result_data:
                out_name = out_name + suffixes[1]
            right_col_map[col] = out_name
            result_data[out_name] = []

        # perform join
        for i in range(len(self)):
            left_key = self._data[left_on][i]
            matching_js = right_index.get(left_key, [])

            if matching_js:
                for j in matching_js:
                    for col in self.columns:
                        result_data[col].append(self._data[col][i])
                    for col, out_name in right_col_map.items():
                        result_data[out_name].append(other._data[col][j])
            else:
                if how == "left":
                    for col in self.columns:
                        result_data[col].append(self._data[col][i])
                    for _, out_name in right_col_map.items():
                        result_data[out_name].append(None)
                elif how == "inner":
                    continue
                else:
                    raise ValueError(f"Unsupported join type: {how}")

        return DataFrame(result_data)


class GroupBy:
    #helper class returned by dataframe.groupby

    def __init__(self, df: DataFrame, group_cols: List[str]):
        self.df = df
        self.group_cols = group_cols

    def agg(self, agg_map: Dict[str, str]) -> DataFrame:
        # Build groups: key -> list of row indices
        groups: Dict[Tuple[Any, ...], List[int]] = {}

        for i in range(len(self.df)):
            key = tuple(self.df._data[col][i] for col in self.group_cols)
            groups.setdefault(key, []).append(i)

        # prep result columns
        result_cols = list(self.group_cols) + list(agg_map.keys())
        result_data: Dict[str, List[Any]] = {c: [] for c in result_cols}

        # helper for computing aggregate
        def compute_agg(values: List[Any], func_name: str) -> Any:
            clean_vals = [v for v in values if v is not None]
            if func_name == "count":
                return len(clean_vals)
            if not clean_vals:
                return None
            if func_name == "sum":
                return sum(clean_vals)
            elif func_name == "max":
                return max(clean_vals)
            elif func_name == "min":
                return min(clean_vals)
            elif func_name == "mean":
                return sum(clean_vals) / len(clean_vals)
            else:
                raise ValueError(f"Unsupported aggregation: {func_name}")

        # compute aggregates
        for key, idxs in groups.items():
            for col, val in zip(self.group_cols, key):
                result_data[col].append(val)

            for target_col, func_name in agg_map.items():
                vals = [self.df._data[target_col][i] for i in idxs]
                agg_val = compute_agg(vals, func_name)
                result_data[target_col].append(agg_val)

        return DataFrame(result_data)


# olist helpers 

def _detect_cat_cols(cat_trans: DataFrame) -> Tuple[str, str | None]:
    
    #Detect the category-name column and the English-name column in the translation table
    
    base_col = None
    eng_col = None

    for col in cat_trans.columns:
        cleaned = col.replace("\ufeff", "")  # remove BOM if present
        if cleaned == "product_category_name":
            base_col = col
        if cleaned == "product_category_name_english":
            eng_col = col

    if base_col is None:
        raise ValueError(
            "Could not find 'product_category_name' column in translation table."
        )
    return base_col, eng_col


def add_category_name_to_order_items(
    order_items: DataFrame,
    products: DataFrame,
    cat_trans: DataFrame,
) -> DataFrame:
    
    #enrich an order_items-like DataFrame with product_category_nameand product_category_name_english.

    
    # Step 1: map product_id → product_category_name
    oi_with_prod = order_items.join(
        products,
        left_on="product_id",
        right_on="product_id",
        how="inner",
    )

    # Step 2: map product_category_name → product_category_name_english
    base_col, _ = _detect_cat_cols(cat_trans)

    full = oi_with_prod.join(
        cat_trans,
        left_on="product_category_name",   # from products
        right_on=base_col,                 # robust to BOM on translation header
        how="left",
    )

    return full


def sort_by_column(df: DataFrame, col: str, ascending: bool = False) -> DataFrame:
    """
    Sort a DataFrame by a specific column.
    ascending=False → descending (useful for top-N by revenue).
    """
    indices = list(range(len(df)))
    indices.sort(key=lambda i: df._data[col][i], reverse=not ascending)
    new_data = {c: [df._data[c][i] for i in indices] for c in df.columns}
    return DataFrame(new_data)


def top_categories_by_revenue(
    order_items: DataFrame,
    products: DataFrame,
    cat_trans: DataFrame,
    top_n: int = 20,
) -> DataFrame:
    
    #Compute the total revenue for each product category (English name if present) and return the top N categories ranked by revenue.

    
    full = add_category_name_to_order_items(order_items, products, cat_trans)
    _, eng_col = _detect_cat_cols(cat_trans)

    # pick grouping col: English if present, else base name
    if eng_col is not None and eng_col in full.columns:
        group_col = eng_col
    else:
        group_col = "product_category_name"

    grouped = full.groupby([group_col]).agg({"price": "sum"})

    result_data = {
        "product_category_name_english": grouped._data[group_col],
        "total_revenue": grouped._data["price"],
    }
    cat_rev = DataFrame(result_data)

    cat_rev_sorted = sort_by_column(cat_rev, "total_revenue", ascending=False)

    top_n = min(top_n, len(cat_rev_sorted))
    truncated_data = {
        col: cat_rev_sorted._data[col][:top_n] for col in cat_rev_sorted.columns
    }

    return DataFrame(truncated_data)
