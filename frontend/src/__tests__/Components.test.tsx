import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { GeometryDataViewer } from "@/components/geometry-data-viewer/GeometryDataViewer";
import { ObjectInspector } from "@/components/object-inspector/ObjectInspector";
import type { GeometryFeature, ProjectObject } from "@/types/api";

describe("Core Provenance & Native Inspection Components", () => {
  it("renders every provenance status accurately", () => {
    const statuses = [
      "original",
      "api_extracted",
      "normalized",
      "computed_by_planswift",
      "derived",
      "ai_inferred",
      "unresolved",
      "unsupported",
    ] as const;
    render(
      <div>
        {statuses.map((s) => (
          <ProvenanceBadge key={s} status={s} />
        ))}
      </div>
    );
    for (const s of statuses) {
      expect(screen.getByText(s)).toBeInTheDocument();
    }
  });

  it("renders GeometryDataViewer as structured coordinates without drawing canvas or raster image", () => {
    const feature: GeometryFeature = {
      id: "geom-1",
      section_guid: "{CB477009-2C9F-49F1-8ADD-42B02D38F149}",
      parent_object_guid: "{1CB26172-81E8-4EA8-A144-805C05A379B7}",
      page_guid: "{A496DDA7-D1E4-4BF2-8A4F-A2B35507BE3E}",
      geometry_type: "PointCollection",
      coordinate_system: "planswift_page_digitizer_raw",
      point_count: 2,
      bbox_min_x: 3224.656,
      bbox_min_y: 755.45,
      bbox_max_x: 3234.371,
      bbox_max_y: 768.663,
      derived_polyline_length: null,
      derived_polygon_area: null,
      provenance: "original",
      derived_metrics_provenance: "derived",
      points: [
        {
          point_order: 0,
          x: 3234.37109375,
          y: 755.450866699219,
          point_type: "Normal",
          raw_x: "3234.37109375",
          raw_y: "755.450866699219",
          normalized_x: null,
          normalized_y: null,
          provenance: "original",
        },
      ],
    };

    const { container } = render(<GeometryDataViewer feature={feature} />);
    expect(screen.getByText("3234.37109375")).toBeInTheDocument();
    expect(container.querySelector("canvas")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders ObjectInspector preserving empty-name properties and formulas", () => {
    const obj: ProjectObject = {
      id: "obj-1",
      project_version: "ver-1",
      native_guid: "{1CB26172-81E8-4EA8-A144-805C05A379B7}",
      native_class: "Count",
      native_type: "Count",
      name: "Duct 250x150mm",
      parent_guid: "{BA630457-834C-481A-AA57-E33D401C9B04}",
      root_path: "project 4/Takeoff/Duct 250x150mm",
      depth: 2,
      order_index: 3,
      is_known_class: true,
      is_measurement_section: false,
      is_page: false,
      page_guid: null,
      group_id: null,
      division: "",
      cost_code: "",
      provenance: "original",
      property_count: 1,
      properties: [
        {
          id: "prop-1",
          native_property_guid: "{02A3C215-A4ED-4721-8C1E-2DC3891BBA23}",
          name: "",
          property_class: "Text",
          raw_value: "",
          parsed_value_json: null,
          normalized_value_json: null,
          normalized_unit: "",
          units: "",
          input_units: "",
          group: "Other",
          order_index: 0,
          decimal_places: "2",
          parse_formula: "-1",
          expression_flag: "",
          is_formula: false,
          is_expression_script: false,
          is_dynamic_page_order: false,
          dynamic_page_guid: "",
          has_image_data: false,
          image_data_length: 0,
          image_data_sha256: "",
          attributes_json: {},
          source_location: "XMLData.XML",
          provenance: "original",
          normalization_provenance: "",
        },
      ],
    };

    render(<ObjectInspector object={obj} />);
    expect(screen.getByText("Duct 250x150mm")).toBeInTheDocument();
    expect(screen.getByText("(empty Name attribute)")).toBeInTheDocument();
  });
});
