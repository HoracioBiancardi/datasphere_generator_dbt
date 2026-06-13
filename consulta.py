from datasphere.datasphere_extractor import DatasphereExtractor, DatasphereConnector
import os

def main():
    connector = DatasphereConnector(
        config={
            "host":os.environ["HANA_ADDRESS"],
             "port": int(os.environ["HANA_PORT"]),
            "user": os.environ["HANA_USER"],
            "password": os.environ["HANA_PASSWORD"],

        }
    )

    extractor = DatasphereExtractor(connector=connector)
    query = "SELECT TOP 1 * FROM IB_SAPECC.DD09L"
    df = extractor.execute_query_to_df(query)
    print(df.columns)

if __name__ == "__main__":
    main()

